import 'dart:convert';

import '../formatters/value_formatters.dart';
import '../network/api_exception.dart';
import '../network/offline_mutations.dart';
import '../network/relay_origin.dart';
import 'cash_register_repository.dart';
import 'entity_catalog.dart';
import 'entity_repository.dart';
import 'fiscal_queue_service.dart';
import 'fiscal_snapshot.dart';
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

  /// UUID da instalação deste terminal — o `nodeId` da topologia local.
  ///
  /// É a identidade que torna a sessão de caixa recuperável ("mesmo operador,
  /// mesma máquina") sem torná-la transferível por acidente. Não usamos MAC,
  /// IP nem nome do computador: nenhum é estável, e nenhum é necessário.
  String? installationId;

  /// Nome amigável do terminal ("Balcão 01"), quando a loja já o nomeou.
  String? terminalLabel;

  /// Operador da sessão atual. Vem do escopo (`servidor|conta:operador`), que
  /// já é o namespace do banco local.
  String? get operatorId {
    final scope = _scope;
    if (scope == null || !scope.contains(':')) return null;
    final actor = scope.split(':').last.trim();
    return actor.isEmpty ? null : actor;
  }

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
  /// Troca IDs temporários já promovidos pelos definitivos.
  ///
  /// Quando a criação sobe, o registro local passa a viver sob o id do
  /// servidor (`EntityRepository.replaceId`) e o temporário só sobrevive no
  /// `id_map`. A TELA, porém, continua segurando o id antigo: ela pediu o
  /// pedido antes de a fila entregar. O resultado era um pedido recém-criado
  /// pela comanda que recusava o primeiro item com "Pedido offline-… não
  /// existe no armazenamento local" — e só voltava a funcionar quando o
  /// operador saía e entrava de novo, porque aí a tela relia o id novo.
  ///
  /// A tradução vale para caminho, filtros e corpo: o id antigo aparece nos
  /// três (`/orders/offline-…/items/`, `?order=offline-…`, `{"order": "…"}`).
  /// Só custa uma consulta quando existe mesmo um id temporário à vista.
  Future<
    ({String path, Map<String, dynamic>? body, Map<String, dynamic>? query})
  >
  _promoted(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
  }) async {
    // O corpo de uma escrita é sempre JSON (é o que vai para a API), mas um
    // valor inesperado no `context` de alguma tela não pode derrubar uma
    // operação que antes passava: sem o retrato serializado, traduz-se ao
    // menos o caminho, que é onde o id aparece na esmagadora maioria dos casos.
    String? probe;
    try {
      probe = jsonEncode({'p': path, 'b': body, 'q': query});
    } catch (_) {
      probe = null;
    }
    if (probe == null) {
      if (!path.contains(LocalId.temporaryPrefix)) {
        return (path: path, body: body, query: query);
      }
      final onlyPath = await queue.resolvedIds(scope: _requireScope());
      var translated = path;
      onlyPath.forEach((local, remote) {
        translated = translated.replaceAll(local, remote);
      });
      return (path: translated, body: body, query: query);
    }
    if (!probe.contains(LocalId.temporaryPrefix)) {
      return (path: path, body: body, query: query);
    }
    final mappings = await queue.resolvedIds(scope: _requireScope());
    if (mappings.isEmpty) return (path: path, body: body, query: query);
    var encoded = probe;
    mappings.forEach((local, remote) {
      encoded = encoded.replaceAll(local, remote);
    });
    final decoded = jsonDecode(encoded) as Map<String, dynamic>;
    return (
      path: '${decoded['p']}',
      body: decoded['b'] is Map
          ? Map<String, dynamic>.from(decoded['b'] as Map)
          : body,
      query: decoded['q'] is Map
          ? Map<String, dynamic>.from(decoded['q'] as Map)
          : query,
    );
  }

  /// A rota é a EMISSÃO de uma nota (a única `/invoices/` que vai para a fila
  /// fiscal)? As outras — consultar autorização, reenviar, cancelar — falam
  /// com o servidor e com a SEFAZ; enfileirá-las criava documento fantasma.
  static bool isFiscalEmission(String path) {
    final clean = path.split('?').first;
    return clean == '/invoices/emit/' || clean == '/invoices/emit';
  }

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
    // A pesagem fecha aqui quando não há outro caminho — e num Caixa
    // Secundário nunca há: ele não fala com a nuvem. O que ele tem é a
    // própria balança na porta serial e a cópia local do cardápio e das
    // comandas, que é tudo de que o fechamento precisa. O pedido é montado
    // neste terminal e entregue ao Caixa Principal pela fila, como qualquer
    // outra venda; a nota de pesagem sai na impressora daqui.
    if (_isScaleCheckout(path)) {
      return relayOnly || !(connectivity?.call() ?? false);
    }
    // A autorização do supervisor continua sendo do servidor: online ela
    // aceita o login de um gerente, algo que só ele sabe validar.
    if (path.endsWith('/approve/')) {
      return !relayOnly && !(connectivity?.call() ?? false);
    }
    if (requiresServer(path)) return false;
    // SÓ A EMISSÃO. `refresh-status`, `resend` e `cancel` também começam com
    // `/invoices/`, e caíam aqui: cada consulta de autorização virava um
    // DOCUMENTO NOVO na fila fiscal, sem pedido (o corpo dessas rotas não tem
    // `order`), que depois tentava emitir sozinho. Consultar a SEFAZ e
    // cancelar uma nota são operações do servidor — sem rede elas não existem.
    if (path.startsWith('/invoices/')) return isFiscalEmission(path);
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
    // E a sessão de caixa nunca é gravada aqui num secundário: quem manda na
    // sessão é o Caixa Principal, e uma cópia local criada por conta própria
    // seria uma segunda sessão esperando para nascer. O secundário encaminha
    // e usa a resposta do principal.
    if (relayOnly && OfflineMutations.ownsCashSession(method, path)) {
      return false;
    }
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
    // A tela pode estar segurando o id que o registro tinha ANTES de a criação
    // subir; aqui ele vira o definitivo.
    final resolved = await _promoted(path, query: query);
    path = resolved.path;
    query = resolved.query;
    final route = EntityCatalog.resolve(path);
    if (route == null) {
      throw ArgumentError('Rota $path não é uma entidade local.');
    }
    final repo = repository(route.type);

    // `/cash-register/current/`: instância única, resolvida por regra.
    if (route.type == EntityCatalog.cashSession && route.action == 'current') {
      final restaurant = '${query?['restaurant'] ?? _restaurantId ?? ''}';
      // A sessão pertence a quem abriu e ao terminal onde foi aberta: devolver
      // a de outra pessoa faria esta tela oferecer sangria e fechamento de uma
      // gaveta que não é dela.
      final origin = RelayOrigin.current;
      final session = await cashRegister.current(
        restaurantId: restaurant.isEmpty ? null : restaurant,
        operatorId: origin?.actorId ?? operatorId,
        installationId: origin?.installationId ?? installationId,
      );
      if (session == null) {
        return {
          'detail': 'Nenhuma sessão de caixa aberta neste terminal.',
          '_local': true,
          '_empty': true,
        };
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
    // Mesmo motivo da leitura: o pedido criado há dez segundos já pode viver
    // sob o id do servidor, e a tela ainda pede pelo temporário. Sem esta
    // tradução, o primeiro item de um pedido novo era recusado com "Pedido
    // offline-… não existe no armazenamento local".
    final resolved = await _promoted(path, body: body, query: query);
    path = resolved.path;
    body = resolved.body;
    query = resolved.query;
    final payload = body ?? const <String, dynamic>{};

    if (_isScaleCheckout(path)) {
      return LocalResult(
        await _writeScaleCheckout(path, payload, context),
        queued: true,
      );
    }

    if (isFiscalEmission(path)) {
      final orderId = '${payload['order'] ?? payload['order_id'] ?? ''}';
      final snapshot = await _captureFiscalSnapshot(orderId, payload);
      final document = await fiscalQueue.enqueue(
        scope: scope,
        orderId: orderId,
        payload: payload,
        snapshot: snapshot?.data,
      );
      // A venda já está concluída; a nota entra na própria fila (§16).
      return LocalResult({
        'id': document.documentId,
        'order': orderId,
        'fiscal_status': document.status.code,
        '_fiscal_pending': true,
        // A tela precisa saber que o retrato saiu incompleto: emitir com
        // cadastro faltando só adia a recusa para a SEFAZ.
        if (snapshot != null && !snapshot.isComplete)
          '_fiscal_issues': snapshot.issues,
      }, queued: true);
    }

    final route = EntityCatalog.resolve(path);
    if (route == null) {
      throw ArgumentError('Rota $path não é uma entidade local.');
    }

    final result = switch (route.type) {
      EntityCatalog.order => await _writeOrder(
        route,
        method,
        path,
        payload,
        context,
      ),
      EntityCatalog.cashSession => await _writeCashRegister(
        route,
        path,
        payload,
        context,
      ),
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
    if (action.startsWith('items/') && action.endsWith('/quantity')) {
      return orders.setItemQuantity(
        orderId,
        itemId: action.split('/')[1],
        quantity: ValueFormatters.number(body['quantity']),
      );
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
      final method = context?['payment_method'] as Map<String, dynamic>?;
      final result = await orders.pay(orderId, body: body, method: method);
      await _mirrorCashSale(body, method, result);
      return result;
    }
    // Remover um recebimento que ainda não subiu é operação deste terminal: o
    // pagamento nunca existiu no servidor, e mandar o `offline-…` para lá só
    // devolvia "não é um UUID válido".
    if (method == 'DELETE' && EntityCatalog.isPendingPaymentAction(action)) {
      return _removePendingPayment(orderId, action.split('/')[1]);
    }
    // PATCH/DELETE direto no pedido.
    return _writeGeneric(route, method, path, body, null);
  }

  /// Captura o retrato fiscal da venda antes de enfileirar a nota (§16).
  ///
  /// Roda no mesmo gesto do pagamento, com o pedido já fechado: é o único
  /// momento em que se sabe, com certeza, o que foi vendido e por qual
  /// cadastro. Falhar aqui não pode derrubar a venda — ela já está paga —,
  /// então o erro vira uma pendência registrada no próprio snapshot.
  Future<FiscalSnapshot?> _captureFiscalSnapshot(
    String orderId,
    Map<String, dynamic> payload,
  ) async {
    if (orderId.isEmpty) return null;
    try {
      final order = await orders.read(orderId);
      if (order == null) return null;
      return await fiscalSnapshotBuilder(repository).build(
        order: order.payload,
        restaurantId: '${order.payload['restaurant'] ?? _restaurantId ?? ''}',
        cpf: '${payload['cpf'] ?? ''}',
        cpfName: '${payload['cpf_name'] ?? ''}',
      );
    } on Object catch (error) {
      return FiscalSnapshot(
        data: const {'snapshot_version': FiscalSnapshotBuilder.version},
        issues: ['Falha ao capturar o retrato fiscal da venda: $error'],
      );
    }
  }

  /// Espelha na gaveta o recebimento em dinheiro que acabou de ser lançado.
  ///
  /// O servidor cria o `CashMovement` junto do pagamento, mas ele só chega
  /// aqui na leitura seguinte da sessão — e até lá o operador via o caixa
  /// parado depois de receber em dinheiro.
  Future<void> _mirrorCashSale(
    Map<String, dynamic> body,
    Map<String, dynamic>? method,
    Map<String, dynamic> result,
  ) async {
    if ('${method?['method_type'] ?? ''}' != 'cash') return;
    final payment = result['_created_payment'] as Map<String, dynamic>?;
    if (payment == null) return;
    final sessionId = '${body['cash_register'] ?? ''}';
    if (sessionId.isEmpty) return;
    // Só o valor APLICADO entra na gaveta: o troco volta para o cliente.
    await cashRegister.registerLocalSale(
      sessionId,
      paymentId: '${payment['id'] ?? ''}',
      amount: ValueFormatters.number(payment['amount']),
      reason: 'Recebimento do pedido',
    );
  }

  /// Desfaz um recebimento que ainda não saiu deste terminal.
  ///
  /// A ordem importa: a operação sai da fila ANTES de o pedido ser reescrito.
  /// Se ela já estiver em entrega (`PROCESSING`), o dinheiro pode já ter sido
  /// aceito lá — e quem desfaz nesse caso é o servidor, com o id definitivo.
  Future<Map<String, dynamic>> _removePendingPayment(
    String orderId,
    String paymentId,
  ) async {
    final scope = _requireScope();
    final discarded = await queue.discardPendingChild(
      scope: scope,
      field: 'client_payment_id',
      clientId: paymentId,
    );
    if (discarded == null) {
      throw ApiException(
        'Este recebimento já está subindo para o servidor. '
        'Aguarde a sincronização para poder removê-lo.',
        statusCode: 409,
      );
    }
    // A sessão sai do corpo da própria operação desfeita: é a gaveta em que
    // aquele dinheiro entrou, e não necessariamente a que está aberta agora.
    await cashRegister.removeLocalSale(
      '${discarded['cash_register'] ?? ''}',
      paymentId: paymentId,
    );
    return orders.removePendingPayment(orderId, paymentId: paymentId);
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
      {...stored.payload, 'current_table': linking ? tableId : null},
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
    // Quando este terminal está executando por outro (o principal atendendo
    // um secundário), o dono da sessão é o DE LÁ — operador e instalação de
    // quem originou. Gravar o operador daqui faria a sessão do PDV 2 nascer
    // no nome do PDV 1.
    final origin = RelayOrigin.current;
    final actor = origin?.actorId ?? operatorId;
    final terminal =
        '${origin?.installationId ?? body['terminal_installation_id'] ?? installationId ?? ''}';
    if (route.isCollection && route.action == 'open') {
      return cashRegister.open(
        body: body,
        restaurantId: '${body['restaurant'] ?? _restaurantId ?? ''}',
        station: context?['cash_station'] as Map<String, dynamic>?,
        operatorName: origin?.actorName.isNotEmpty == true
            ? origin!.actorName
            : context?['operator_name'] as String?,
        operatorId: actor,
        installationId: terminal.isEmpty ? null : terminal,
        terminalLabel:
            '${origin?.terminalName ?? body['terminal_name'] ?? terminalLabel ?? ''}',
      );
    }
    final id = route.entityId ?? '';
    switch (route.action) {
      case 'close':
        return cashRegister.close(
          id,
          body: body,
          operatorId: actor,
          installationId: terminal.isEmpty ? null : terminal,
        );
      case 'withdrawal':
        return cashRegister.registerMovement(
          id,
          movementType: 'withdrawal',
          body: body,
          operatorId: actor,
          installationId: terminal.isEmpty ? null : terminal,
        );
      case 'supply':
        return cashRegister.registerMovement(
          id,
          movementType: 'supply',
          body: body,
          operatorId: actor,
          installationId: terminal.isEmpty ? null : terminal,
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
      // O recebimento em dinheiro também deixou um lançamento na gaveta deste
      // terminal, com o id temporário do pagamento. Ele precisa apontar para o
      // id que o servidor confirmou: enquanto for temporário, a leitura da
      // sessão o preserva — e passaria a somar o mesmo dinheiro do movimento
      // que o servidor já devolve.
      final sessionId = '${entry.payload?['cash_register'] ?? ''}';
      if (sessionId.isNotEmpty) {
        await cashRegister.replaceReference(sessionId, childLocalId, realId);
      }
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
      // Recusa fiscal e erro de configuracao saem de `fiscal_pending` porque
      // esperar nao os resolve — sem esta linha eles sumiriam do diagnostico.
      'fiscal_blocked': await fiscalQueue.blockedCount(scope: scope),
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
