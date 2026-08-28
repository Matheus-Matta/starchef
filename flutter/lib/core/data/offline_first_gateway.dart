import 'dart:convert';

import '../network/api_exception.dart';
import '../network/offline_mutations.dart';
import 'cash_register_repository.dart';
import 'entity_catalog.dart';
import 'entity_repository.dart';
import 'fiscal_queue_service.dart';
import 'local_id.dart';
import 'order_repository.dart';
import 'payload_cipher.dart';
import 'print_queue_service.dart';
import 'pdv_database.dart';
import 'sync_operation.dart';
import 'sync_queue_service.dart';

/// Resultado de uma operação atendida localmente.
class LocalResult {
  const LocalResult(this.payload, {this.queued = false});

  final Map<String, dynamic> payload;

  /// A operação entrou na fila e ainda precisa subir.
  final bool queued;
}

/// Roteador offline-first: o ponto onde o PDV deixou de perguntar à rede.
///
/// **Leitura** (§3): a rota é resolvida contra o [EntityCatalog] e respondida
/// pelo SQLite na hora. A sincronização com o backend é disparada em paralelo
/// e nunca é esperada.
///
/// **Escrita** (§4): a alteração é aplicada no SQLite e enfileirada na mesma
/// transação, e a resposta volta imediatamente. Se a API estiver fora, a
/// operação simplesmente permanece na fila.
///
/// O que continua exigindo servidor é só o que não pode ser feito de outro
/// jeito: autenticação, leitura física de balança, trabalhos de impressão do
/// backend e aprovação de supervisor. A emissão fiscal deixou de ser exceção —
/// ela tem fila própria (§16).
class OfflineFirstGateway {
  OfflineFirstGateway({
    required this.database,
    required this.queue,
    required this.fiscalQueue,
    PrintQueueService? printQueue,
    PayloadCipher? cipher,
    this.serviceFeePercent = 10,
  }) : printQueue = printQueue ?? PrintQueueService(database: database),
       _cipher = cipher ?? PayloadCipher.disabled();

  /// Rotas que nenhum armazenamento local pode responder.
  ///
  /// A lista encolheu de propósito em relação à anterior: abrir, fechar e
  /// movimentar caixa saíram daqui porque §30 exige que o turno funcione sem
  /// internet, e `/invoices/` saiu porque a emissão agora tem fila própria
  /// (§16) — a venda conclui, o documento espera.
  static const _serverOnlyFragments = [
    '/auth/',
    '/cash-auth/',
    '/print-jobs/',
    // Não é uma coleção de entidades: devolve `{"templates": [...]}` sem id.
    // Quem guarda esses arquivos localmente é o `PrintTemplateCache`.
    '/printers/templates/',
    '/scales/readings/',
    'latest-reading',
    'checkout-command',
    'claim-agent',
    'release-agent',
    'mark-printed',
    'mark-failed',
    'test-connection',
    '/print/',
    '/reports/',
  ];

  final PdvDatabase database;
  final SyncQueueService queue;
  final FiscalQueueService fiscalQueue;

  /// Fila de impressão deste terminal (§17). Um cupom montado aqui e um
  /// `PrintJob` vindo do servidor esperam no mesmo lugar.
  final PrintQueueService printQueue;
  final PayloadCipher _cipher;

  /// Percentual de taxa de serviço usado no fechamento offline.
  double serviceFeePercent;

  /// Este terminal é um **Caixa Secundário**: ele grava e enfileira do mesmo
  /// jeito, mas quem recebe a fila é o Caixa Principal, não a nuvem (§8).
  ///
  /// A diferença prática está no que ele aceita gravar: só o que o principal
  /// sabe executar pela rede local. Aceitar mais aqui deixaria o operador com
  /// uma operação salva que nunca teria como ser entregue.
  bool relayOnly = false;

  /// Há conexão com o servidor agora? Consultado **apenas** pela pesagem.
  ///
  /// A pesagem é a única rota que continua preferindo o servidor quando ele
  /// responde: online, é ele quem liga a leitura ao item, numera o pedido e
  /// renderiza a nota. Interceptá-la sempre degradaria o fluxo normal do
  /// buffet só para atender o caso da rede caída. Aqui, portanto, o local é
  /// alternativa — não o primeiro caminho.
  bool Function()? connectivity;

  String? _scope;
  String? _restaurantId;
  final Map<String, EntityRepository> _repositories = {};

  /// Namespace da sessão (servidor + conta + operador). Sem ele o gateway não
  /// atende nada: dados de duas contas não podem se misturar no mesmo
  /// terminal.
  String? get scope => _scope;

  String? get restaurantId => _restaurantId;

  void bindSession({required String scope, String? restaurantId}) {
    if (_scope != scope) _repositories.clear();
    _scope = scope;
    _restaurantId = restaurantId ?? _restaurantId;
  }

  void bindRestaurant(String? restaurantId) => _restaurantId = restaurantId;

  void clearSession() {
    _scope = null;
    _repositories.clear();
  }

  /// Repositório do tipo pedido, criando-o na primeira vez.
  EntityRepository repository(String type) {
    final scope = _requireScope();
    return _repositories.putIfAbsent(type, () {
      if (type == EntityCatalog.order) {
        return OrderRepository(
          database: database,
          scope: scope,
          products: repository(EntityCatalog.product),
          cipher: _cipher,
        );
      }
      if (type == EntityCatalog.cashSession) {
        return CashRegisterRepository(
          database: database,
          scope: scope,
          cipher: _cipher,
        );
      }
      final descriptor = EntityCatalog.byType(type);
      if (descriptor == null) {
        throw ArgumentError('Tipo de entidade desconhecido: $type');
      }
      return EntityRepository(
        database: database,
        descriptor: descriptor,
        scope: scope,
        cipher: _cipher,
      );
    });
  }

  OrderRepository get orders =>
      repository(EntityCatalog.order) as OrderRepository;

  CashRegisterRepository get cashRegister =>
      repository(EntityCatalog.cashSession) as CashRegisterRepository;

  /// Repositório correspondente à rota, ou `null` se ela não for de entidade.
  EntityRepository? repositoryForPath(String path) {
    final route = EntityCatalog.resolve(path);
    if (route == null) return null;
    return repository(route.type);
  }

  // ------------------------------------------------------------- roteamento

  /// A rota exige servidor de verdade?
  static bool requiresServer(String path) =>
      _serverOnlyFragments.any(path.contains);

  /// O gateway sabe responder esta leitura pelo SQLite?
  bool handlesRead(String path) {
    if (_scope == null || requiresServer(path)) return false;
    final route = EntityCatalog.resolve(path);
    if (route == null) return false;
    // Subcoleções e relatórios pendurados no recurso não são o recurso: só as
    // leituras que o banco local sabe montar de verdade passam por aqui.
    return route.action == null ||
        route.action == 'current' ||
        (route.type == EntityCatalog.order && route.action == 'payments');
  }

  /// O gateway sabe aplicar esta escrita no SQLite?
  bool handlesWrite(String method, String path, Map<String, dynamic>? body) {
    if (_scope == null || method == 'GET') return false;
    // A ordem importa: `/invoices/<id>/print/` contém `/print/` e é uma
    // operação de servidor de verdade (renderiza o DANFE). Só a EMISSÃO vai
    // para a fila fiscal.
    // A pesagem fecha na comanda sem servidor: o peso é lido pela porta
    // serial e o item entra no pedido local. Só a `ScaleReading` exige
    // servidor, e ela é materializada no replay a partir do peso bruto.
    // Duas rotas continuam preferindo o servidor quando ele responde, e só
    // caem para o local quando ele não responde:
    //
    // - a pesagem, porque online é o servidor que liga a leitura ao item,
    //   numera o pedido e renderiza a nota;
    // - a autorização do caixa, porque online ela também aceita o login de um
    //   gerente — algo que só o servidor sabe validar.
    //
    // Interceptá-las sempre degradaria o fluxo normal só para atender o caso
    // da rede caída. Aqui, portanto, o local é alternativa, não primeiro
    // caminho.
    if (_isScaleCheckout(path) || path.endsWith('/approve/')) {
      return !relayOnly && !(connectivity?.call() ?? false);
    }
    if (requiresServer(path)) return false;
    if (path.startsWith('/invoices/')) return true;
    // Uma leitura física de balança é um registro do servidor criado no
    // instante da pesagem: enfileirá-la depois não faz sentido. O peso em si
    // (`weight_kg`, `tare_kg`) é apenas um valor e viaja normalmente — sem
    // isso não daria para vender a granel offline, que §30 exige.
    if (body?['scale_reading'] != null) return false;
    final route = EntityCatalog.resolve(path);
    if (route == null) return false;
    // Uma ação que o banco local não sabe aplicar precisa do servidor. Sem
    // esta checagem ela caía no caminho genérico e era interpretada como uma
    // alteração no próprio recurso.
    if (!EntityCatalog.isLocalAction(route.type, route.action)) return false;
    // Num secundário, a fila só pode aceitar o que o principal sabe receber.
    if (relayOnly && !OfflineMutations.isRelayable(method, path)) return false;
    return true;
  }

  /// Tipos que este terminal deve baixar. Num secundário, o principal não
  /// entrega dado fiscal nem cadastro de usuários.
  List<EntityDescriptor> get pullOrder => EntityCatalog.pullOrder
      .where((item) => !relayOnly || item.sharedWithSecondary)
      .toList();

  // ---------------------------------------------------------------- leitura

  /// Responde a leitura pelo SQLite (§3).
  Future<Map<String, dynamic>> read(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final route = EntityCatalog.resolve(path);
    if (route == null) {
      throw ArgumentError('Rota $path não é uma entidade local.');
    }
    final repo = repository(route.type);

    // `/cash-register/current/`: instância única, resolvida por regra.
    if (route.type == EntityCatalog.cashSession && route.action == 'current') {
      final session = await cashRegister.current(
        restaurantId: '${query?['restaurant'] ?? _restaurantId ?? ''}'.isEmpty
            ? null
            : '${query?['restaurant'] ?? _restaurantId}',
      );
      if (session == null) {
        return {'detail': 'Nenhuma sessão de caixa aberta neste terminal.',
          '_local': true, '_empty': true};
      }
      return {...session, '_local': true};
    }

    if (route.isCollection) {
      final page = await repo.list(query: query);
      return page.toJson(basePath: route.descriptor.collectionPath);
    }

    // Subcoleção conhecida: pagamentos de um pedido.
    if (route.type == EntityCatalog.order && route.action == 'payments') {
      final payments = await orders.payments(route.entityId!);
      return {
        'count': payments.length,
        'next': null,
        'previous': null,
        'results': payments,
        '_local': true,
      };
    }

    final record = await repo.read(route.entityId!);
    if (record == null) {
      return {
        'detail': 'Registro não encontrado no armazenamento local.',
        '_local': true,
        '_empty': true,
      };
    }
    return {...record.toApiJson(), '_local': true};
  }

  // ---------------------------------------------------------------- escrita

  /// Aplica a escrita no SQLite e enfileira a sincronização (§4).
  Future<LocalResult> write(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    Map<String, dynamic>? context,
  }) async {
    final scope = _requireScope();
    final payload = body ?? const <String, dynamic>{};

    if (_isScaleCheckout(path)) {
      return LocalResult(
        await _writeScaleCheckout(path, payload, context),
        queued: true,
      );
    }

    if (path.startsWith('/invoices/')) {
      final orderId = '${payload['order'] ?? payload['order_id'] ?? ''}';
      final document = await fiscalQueue.enqueue(
        scope: scope,
        orderId: orderId,
        payload: payload,
      );
      // A venda já está concluída; a nota entra na própria fila (§16).
      return LocalResult({
        'id': document.documentId,
        'order': orderId,
        'fiscal_status': document.status.code,
        '_fiscal_pending': true,
      }, queued: true);
    }

    final route = EntityCatalog.resolve(path);
    if (route == null) {
      throw ArgumentError('Rota $path não é uma entidade local.');
    }

    final result = switch (route.type) {
      EntityCatalog.order => await _writeOrder(route, method, path, payload, context),
      EntityCatalog.cashSession => await _writeCashRegister(route, path, payload, context),
      EntityCatalog.command when route.action != null =>
        await _writeCommandTableLink(route, path, payload),
      _ => await _writeGeneric(route, method, path, payload, query),
    };
    return LocalResult(result, queued: true);
  }

  Future<Map<String, dynamic>> _writeOrder(
    EntityRoute route,
    String method,
    String path,
    Map<String, dynamic> body,
    Map<String, dynamic>? context,
  ) async {
    if (route.isCollection) {
      return orders.createOrder(
        path: path,
        body: body,
        restaurantId: '${body['restaurant'] ?? _restaurantId ?? ''}',
        table: context?['table'] as Map<String, dynamic>?,
        command: context?['command'] as Map<String, dynamic>?,
      );
    }

    final orderId = route.entityId!;
    final action = route.action ?? '';
    if (action == 'items') {
      return orders.addItem(orderId, body: body);
    }
    if (action.startsWith('items/') && action.endsWith('/void')) {
      final itemId = action.split('/')[1];
      return orders.voidItem(orderId, itemId: itemId, body: body);
    }
    if (action == 'send-to-kitchen') {
      return orders.sendToKitchen(orderId, body: body);
    }
    if (action == 'close') {
      return orders.close(
        orderId,
        body: body,
        serviceFeePercent: serviceFeePercent,
      );
    }
    if (action == 'pay') {
      return orders.pay(
        orderId,
        body: body,
        method: context?['payment_method'] as Map<String, dynamic>?,
      );
    }
    // PATCH/DELETE direto no pedido.
    return _writeGeneric(route, method, path, body, null);
  }

  static final _scaleCheckout = RegExp(r'^/scales/([^/]+)/checkout-command/$');

  static bool _isScaleCheckout(String path) =>
      _scaleCheckout.hasMatch(path.split('?').first);

  /// Fecha a pesagem na comanda usando só o que está no terminal.
  ///
  /// A tela informa a comanda, o produto pesado e os extras: nada disso é
  /// resolvido pela API. O peso vem da porta serial da balança, que já era
  /// local.
  Future<Map<String, dynamic>> _writeScaleCheckout(
    String path,
    Map<String, dynamic> body,
    Map<String, dynamic>? context,
  ) async {
    final scaleId = _scaleCheckout.firstMatch(path.split('?').first)!.group(1)!;
    final product = context?['weighed_product'] as Map<String, dynamic>?;
    if (product == null) {
      throw ArgumentError('A pesagem local precisa do produto pesado.');
    }
    final code = '${body['command_code'] ?? ''}'.trim();
    final command =
        context?['command'] as Map<String, dynamic>? ??
        await _findCommandByCode(code);
    if (command == null) {
      throw ApiException(
        'Comanda $code não encontrada na cópia local deste terminal.',
        statusCode: 404,
      );
    }
    return orders.checkoutCommand(
      scaleId: scaleId,
      command: command,
      weighedProduct: product,
      weightKg: double.tryParse('${body['weight_kg'] ?? 0}') ?? 0,
      extras: (body['extras'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList(),
      restaurantId: _restaurantId,
      printedLocally: body['offline_printed'] == true,
    );
  }

  /// Acha a comanda pelo código ou pelo número, como o backend faz.
  Future<Map<String, dynamic>?> _findCommandByCode(String code) async {
    if (code.isEmpty) return null;
    final repo = repository(EntityCatalog.command);
    final page = await repo.list(query: {'page_size': 500});
    for (final command in page.results) {
      if ('${command['code'] ?? ''}' == code) return command;
    }
    final asNumber = int.tryParse(code);
    if (asNumber == null) return null;
    for (final command in page.results) {
      if (command['number'] == asNumber) return command;
    }
    return null;
  }

  /// Vincula ou desvincula a mesa da comanda (§30: abrir e transferir mesa).
  ///
  /// A tela lê `current_table` da comanda; mesclar o corpo cru gravaria um
  /// campo `table` que ninguém consulta, e o salão continuaria sem saber onde
  /// o cliente sentou até a operação subir.
  Future<Map<String, dynamic>> _writeCommandTableLink(
    EntityRoute route,
    String path,
    Map<String, dynamic> body,
  ) async {
    final repo = repository(EntityCatalog.command);
    final commandId = route.entityId ?? '';
    final stored = await repo.read(commandId);
    if (stored == null) {
      throw StateError('Comanda $commandId não existe no armazenamento local.');
    }
    final linking = route.action == 'link-table';
    // O contrato do backend é `table_id` (ver `CommandViewSet.link_table`);
    // `table` é aceito só por tolerância a chamadas antigas.
    final tableId = body['table_id'] ?? body['table'];
    final record = await repo.saveLocal(
      {
        ...stored.payload,
        'current_table': linking ? tableId : null,
      },
      operation: SyncOperation.update,
      method: 'POST',
      path: path,
      requestBody: body,
      id: commandId,
    );
    return record.toApiJson();
  }

  Future<Map<String, dynamic>> _writeCashRegister(
    EntityRoute route,
    String path,
    Map<String, dynamic> body,
    Map<String, dynamic>? context,
  ) async {
    if (route.isCollection && route.action == 'open') {
      return cashRegister.open(
        body: body,
        restaurantId: '${body['restaurant'] ?? _restaurantId ?? ''}',
        station: context?['cash_station'] as Map<String, dynamic>?,
        operatorName: context?['operator_name'] as String?,
      );
    }
    final id = route.entityId ?? '';
    switch (route.action) {
      case 'close':
        return cashRegister.close(id, body: body);
      case 'withdrawal':
        return cashRegister.registerMovement(
          id,
          movementType: 'withdrawal',
          body: body,
        );
      case 'supply':
        return cashRegister.registerMovement(
          id,
          movementType: 'supply',
          body: body,
        );
      case 'approve':
        return cashRegister.approve(
          id,
          body: body,
          movementId: '${body['movement'] ?? ''}',
          approverName: context?['approver_name'] as String?,
        );
    }
    throw ArgumentError('Operação de caixa não suportada localmente: $path');
  }

  Future<Map<String, dynamic>> _writeGeneric(
    EntityRoute route,
    String method,
    String path,
    Map<String, dynamic> body,
    Map<String, dynamic>? query,
  ) async {
    final repo = repository(route.type);
    final operation = SyncOperation.fromMethod(method);

    if (route.isCollection && operation == SyncOperation.create) {
      final id = '${body['id'] ?? ''}'.isEmpty
          ? LocalId.temporary()
          : '${body['id']}';
      final record = await repo.saveLocal(
        {
          ...body,
          'id': id,
          'created_at': DateTime.now().toUtc().toIso8601String(),
          'updated_at': DateTime.now().toUtc().toIso8601String(),
        },
        operation: SyncOperation.create,
        method: method,
        path: path,
        query: query,
        requestBody: body,
        id: id,
      );
      return record.toApiJson();
    }

    final entityId = route.entityId ?? '${body['id'] ?? ''}';
    final existing = await repo.read(entityId, includeDeleted: true);
    final merged = {...?existing?.payload, ...body, 'id': entityId};
    final record = await repo.saveLocal(
      merged,
      operation: operation,
      method: method,
      path: path,
      query: query,
      requestBody: body,
      id: entityId,
    );
    return record.toApiJson();
  }

  // ------------------------------------------------------------- utilidades

  /// Persiste uma resposta de coleção vinda da API (§14).
  ///
  /// Só a coleção do recurso. `/orders/<id>/payments/` também devolve
  /// `results`, mas são pagamentos — gravá-los aqui criaria um "pedido" para
  /// cada recebimento, com o id do pagamento.
  Future<int> applyRemoteCollection(
    String path,
    Map<String, dynamic> response,
  ) async {
    final route = EntityCatalog.resolve(path);
    if (route == null || _scope == null) return 0;
    if (!route.isCollection || route.action != null) return 0;
    final results = response['results'];
    final items = results is List
        ? results
              .whereType<Map>()
              .map((item) => Map<String, dynamic>.from(item))
              .toList()
        : <Map<String, dynamic>>[];
    if (items.isEmpty && results is! List && response['id'] != null) {
      final record = await repository(route.type).applyRemote(response);
      return record == null ? 0 : 1;
    }
    return repository(route.type).applyRemoteList(items);
  }

  /// Persiste uma resposta de detalhe vinda da API.
  Future<void> applyRemoteDetail(
    String path,
    Map<String, dynamic> response,
  ) async {
    final route = EntityCatalog.resolve(path);
    if (route == null || _scope == null) return;
    if (response['id'] == null) return;
    // Uma ação sobre o recurso (`/orders/<id>/close/`) responde outra coisa
    // que não o recurso; só o detalhe puro é gravado.
    if (route.isCollection || route.action != null) return;
    if ('${response['id']}' != route.entityId) return;
    await repository(route.type).applyRemote(response);
  }

  /// Identificadores que o terminal cria para um sub-recurso ANTES de a
  /// operação subir (§7). O nome viaja no corpo para que o servidor possa
  /// deduplicar, e volta aqui para reconciliar a cópia local.
  static const _clientChildIdKeys = [
    'client_item_id',
    'client_payment_id',
    'client_movement_id',
  ];

  /// Confirma no banco a entrega de uma operação da fila.
  Future<void> confirmDelivery(
    SyncQueueEntry entry,
    Map<String, dynamic> response,
  ) async {
    final scope = _requireScope();
    final repo = _repositoryForType(entry.entityType);
    if (repo == null) return;
    // Nem toda ação responde o recurso direto: a pesagem devolve
    // `{order, weighed_item, print_job}`. Sem desembrulhar, o identificador
    // temporário do pedido nunca era trocado pelo real — e a próxima leitura
    // do servidor trazia a MESMA venda como um segundo pedido na tela.
    final entityPayload = _entityPayloadOf(entry.entityType, response);
    final realId = '${entityPayload['id'] ?? ''}';

    // A própria entidade foi criada: o identificador temporário vira o real
    // em todo lugar — banco, fila e referências pendentes.
    if (LocalId.isTemporary(entry.entityId) && realId.isNotEmpty) {
      await queue.registerResolvedId(
        scope: scope,
        localId: entry.entityId,
        remoteId: realId,
      );
      await repo.replaceId(entry.entityId, realId);
      await repo.markSynced(
        realId,
        serverPayload: entityPayload,
        ignoreQueuedOperationId: entry.operationId,
      );
      return;
    }

    // Um sub-recurso foi criado dentro dela (item, pagamento, sangria): a
    // resposta traz o id definitivo DELE, não o do pai.
    final childLocalId = _clientChildIdKeys
        .map((key) => '${entry.payload?[key] ?? ''}')
        .firstWhere(LocalId.isTemporary, orElse: () => '');
    if (childLocalId.isNotEmpty && realId.isNotEmpty) {
      await queue.registerResolvedId(
        scope: scope,
        localId: childLocalId,
        remoteId: realId,
      );
      await repo.replaceReference(entry.entityId, childLocalId, realId);
    }
    await repo.markSynced(
      entry.entityId,
      serverPayload: entityPayload,
      ignoreQueuedOperationId: entry.operationId,
    );
  }

  /// Desembrulha o recurso quando a resposta é um envelope.
  ///
  /// `POST /scales/<id>/checkout-command/` responde
  /// `{order, weighed_item, extra_items, print_job}` — o pedido está dentro,
  /// não no topo.
  static Map<String, dynamic> _entityPayloadOf(
    String entityType,
    Map<String, dynamic> response,
  ) {
    if (response['id'] != null) return response;
    const envelopeKey = <String, String>{
      EntityCatalog.order: 'order',
      EntityCatalog.cashSession: 'cash_register',
    };
    final nested = response[envelopeKey[entityType] ?? entityType];
    return nested is Map ? Map<String, dynamic>.from(nested) : response;
  }

  /// Marca a entidade como recusada, para a tela de revisão.
  Future<void> markDeliveryFailed(SyncQueueEntry entry) async {
    await _repositoryForType(entry.entityType)?.markFailed(entry.entityId);
  }

  EntityRepository? _repositoryForType(String type) =>
      EntityCatalog.byType(type) == null ? null : repository(type);

  /// Marca de tempo da última sincronização de um tipo (§14).
  Future<DateTime?> lastSyncAt(String entityType) async {
    final scope = _scope;
    if (scope == null) return null;
    final row = await database.querySingle(
      'SELECT last_sync_at FROM sync_state WHERE scope = ? AND entity_type = ?',
      [scope, entityType],
    );
    return DateTime.tryParse('${row?['last_sync_at'] ?? ''}')?.toUtc();
  }

  Future<void> recordSync(
    String entityType, {
    DateTime? at,
    String? error,
  }) async {
    final scope = _scope;
    if (scope == null) return;
    await database.execute(
      '''
      INSERT INTO sync_state(scope, entity_type, last_sync_at, last_error)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(scope, entity_type) DO UPDATE SET
        last_sync_at = COALESCE(excluded.last_sync_at, sync_state.last_sync_at),
        last_error = excluded.last_error
      ''',
      [
        scope,
        entityType,
        (at ?? DateTime.now().toUtc()).toIso8601String(),
        error,
      ],
    );
  }

  /// Estado agregado da operação local, usado pela barra de sincronização.
  Future<Map<String, dynamic>> diagnostics() async {
    final scope = _scope;
    if (scope == null) return const {'bound': false};
    final summary = await queue.summary(scope: scope);
    final printing = await printQueue.summary(scope: scope);
    final counts = await database.query(
      '''
      SELECT entity_type, COUNT(*) AS total FROM entities
      WHERE scope = ? AND deleted_at IS NULL
      GROUP BY entity_type
      ''',
      [scope],
    );
    return {
      'bound': true,
      'scope': scope,
      'queue': {
        'pending': summary.pending,
        'processing': summary.processing,
        'failed': summary.failed,
      },
      'fiscal_pending': await fiscalQueue.pendingCount(scope: scope),
      'print_queue': {'pending': printing.pending, 'failed': printing.failed},
      'entities': {
        for (final row in counts)
          '${row['entity_type']}': (row['total'] as num?)?.toInt() ?? 0,
      },
    };
  }

  String _requireScope() {
    final scope = _scope;
    if (scope == null) {
      throw StateError(
        'O armazenamento local ainda não foi vinculado a uma sessão.',
      );
    }
    return scope;
  }

  /// Serialização usada nos logs de diagnóstico.
  static String describe(Map<String, dynamic> value) => jsonEncode(value);
}
