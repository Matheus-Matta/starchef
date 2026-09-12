import 'package:sqlite_async/sqlite_async.dart';

import '../formatters/input_values.dart';
import '../formatters/decimal_money.dart';
import '../network/api_exception.dart';
import 'cash_session_status.dart';
import 'entity_catalog.dart';
import 'entity_record.dart';
import 'entity_repository.dart';
import 'local_id.dart';
import 'sync_operation.dart';

/// O caixa já está ocupado por outra sessão — ou por outro dono.
///
/// É o equivalente local do 409 do backend: no Caixa Principal, com a internet
/// fora, é ESTA exceção que impede o segundo operador de abrir o mesmo caixa.
/// Sem ela, a exclusividade só existiria quando houvesse rede — exatamente
/// quando ela menos importa.
///
/// É uma [ApiException] de propósito: a tela já sabe mostrar uma recusa do
/// servidor, e para o operador não faz diferença alguma se quem recusou foi a
/// nuvem ou o Caixa Principal. O que muda é só a mensagem, e ela é a mesma.
class CashSessionConflict extends ApiException {
  const CashSessionConflict(
    super.message, {
    this.session,
    this.code = 'cash_session_conflict',
  }) : super(statusCode: 409);

  final Map<String, dynamic>? session;
  final String code;
}

/// Sessão de caixa guardada localmente (§15 Caixa, §30).
///
/// Antes, abrir e fechar caixa exigiam servidor: `/cash-register/` estava na
/// lista de rotas que só funcionavam online, e a cópia local existia apenas
/// para "informar em qual sessão os pedidos entram". Isso contraria a regra
/// fundamental — com a internet fora, o turno não começava.
///
/// Aqui a sessão, o saldo, as sangrias e os suprimentos são registros locais
/// como qualquer outro; a API recebe tudo quando a conexão voltar.
class CashRegisterRepository extends EntityRepository {
  CashRegisterRepository({
    required super.database,
    required super.scope,
    super.cipher,
  }) : super(descriptor: _descriptor);

  static final EntityDescriptor _descriptor =
      EntityCatalog.byType(EntityCatalog.cashSession)!;

  /// Sessão em andamento deste operador, neste terminal — se houver.
  ///
  /// Espelha `/cash-register/current/` **com a regra de dono**: a sessão
  /// pertence a quem a abriu e à máquina onde foi aberta. Devolver aqui a
  /// sessão de outra pessoa faria o terminal offline oferecer sangria e
  /// fechamento de uma gaveta que não é dele.
  ///
  /// Reiniciar o terminal ou logar de novo continua funcionando: o dono é o
  /// par (operador, instalação), não a sessão HTTP.
  Future<Map<String, dynamic>?> current({
    String? restaurantId,
    String? operatorId,
    String? installationId,
  }) async {
    final page = await list(
      query: {
        'restaurant': ?restaurantId,
        'page_size': 50,
      },
    );
    for (final session in page.results) {
      if (CashSessionStatus.isFinished(session['status'])) continue;
      if (!_belongsTo(session, operatorId: operatorId, installationId: installationId)) {
        continue;
      }
      return session;
    }
    return null;
  }

  /// A sessão ocupando este caixa, seja de quem for (para explicar o bloqueio).
  Future<Map<String, dynamic>?> occupying(String? stationId, {String? restaurantId}) async {
    if (stationId == null || stationId.isEmpty) return null;
    final page = await list(query: {'restaurant': ?restaurantId, 'page_size': 50});
    for (final session in page.results) {
      if (CashSessionStatus.isFinished(session['status'])) continue;
      if ('${session['cash_station'] ?? ''}' == stationId) return session;
    }
    return null;
  }

  /// A sessão é deste operador nesta instalação?
  ///
  /// Espelho exato de `session_belongs_to` (`apps/payments/terminals.py`). O
  /// caixa é uma gaveta física: cada terminal cuida do seu, offline inclusive.
  /// Afrouxar qualquer um dos três degraus abaixo faz um terminal adotar a
  /// gaveta de outro — foi assim que o Caixa Secundário passou a mostrar a
  /// sessão aberta no Principal.
  static bool _belongsTo(
    Map<String, dynamic> session, {
    String? operatorId,
    String? installationId,
  }) {
    // 1. Dono. Não saber quem está na frente do terminal não autoriza a
    //    adotar a sessão de ninguém: sem identidade, nada é "meu".
    final owner = '${session['opened_by'] ?? ''}';
    final actor = operatorId ?? '';
    if (owner.isNotEmpty && (actor.isEmpty || owner != actor)) return false;

    // 2. Sessão sem máquina registrada (base anterior ao PdvTerminal): não há
    //    o que comparar, e a checagem por operador já decidiu.
    final terminal = '${session['opened_terminal_installation_id'] ?? ''}';
    if (terminal.isEmpty) return true;

    // 3. A sessão TEM dona de máquina. Se esta instalação não se identificou,
    //    ela é outra máquina — como no servidor. Afrouxar aqui anularia a
    //    regra, porque bastaria não conhecer a própria identidade para
    //    herdar a gaveta do vizinho.
    return terminal == (installationId ?? '');
  }

  /// O nome do caixa desta sessão, para mostrar ao operador.
  ///
  /// `cash_station_name` PRIMEIRO, sempre. `station` é um campo de texto
  /// livre herdado, cujo padrão — no model do backend e no payload local — é
  /// a string literal `"PDV principal"`, e NINGUÉM nunca a preenche com outra
  /// coisa: nenhum cliente envia `station` ao abrir o caixa. Ler esse campo na
  /// tela fazia todo terminal exibir "PDV principal" no lugar do nome do
  /// caixa de verdade — o que, num Caixa Secundário, se parecia exatamente
  /// com "estou vendo o caixa do Principal".
  static String stationLabelOf(
    Map<String, dynamic> session, {
    String fallback = 'caixa',
  }) {
    final name = '${session['cash_station_name'] ?? ''}'.trim();
    if (name.isNotEmpty) return name;
    final legacy = '${session['station'] ?? ''}'.trim();
    // O literal herdado não descreve terminal nenhum: exibi-lo num Caixa
    // Secundário se parece exatamente com "estou vendo o caixa do Principal",
    // que é o defeito que este método existe para não repetir.
    if (legacy.isNotEmpty && legacy != _misleadingLegacyStation) return legacy;
    // Sem caixa cadastrado, o nome honesto é o do próprio terminal.
    final terminal = '${session['opened_terminal_label'] ?? ''}'.trim();
    return terminal.isNotEmpty ? terminal : fallback;
  }

  /// O padrão do model no backend, que nenhum cliente preenche.
  static const _misleadingLegacyStation = 'PDV principal';

  /// Mensagem de bloqueio, no mesmo formato do backend.
  static String occupiedMessage(Map<String, dynamic> session) {
    final station = stationLabelOf(session);
    final operator = '${session['opened_by_name'] ?? ''}';
    final terminal = '${session['opened_terminal_label'] ?? ''}';
    final openedAt = DateTime.tryParse('${session['opened_at'] ?? ''}')?.toLocal();
    final by = operator.isEmpty ? '' : ' por $operator';
    final where = terminal.isEmpty ? '' : ' no terminal $terminal';
    final since = openedAt == null
        ? ''
        : ' desde ${_two(openedAt.day)}/${_two(openedAt.month)}/${openedAt.year}'
              ' às ${_two(openedAt.hour)}:${_two(openedAt.minute)}';
    return 'O $station já está aberto$by$where$since. '
        'Finalize a sessão ou solicite uma transferência gerencial.';
  }

  static String _two(int value) => value.toString().padLeft(2, '0');

  /// Abre a sessao — recusando na hora se o caixa ja estiver ocupado.
  ///
  /// O Caixa Principal e a autoridade da loja: com a internet fora, e aqui que
  /// a exclusividade tem de valer. A checagem roda DENTRO da transacao que
  /// grava a abertura ([saveLocal] com `guard`), entao duas aberturas
  /// simultaneas nao conseguem as duas ler "livre" antes de gravar.
  Future<Map<String, dynamic>> open({
    required Map<String, dynamic> body,
    required String? restaurantId,
    Map<String, dynamic>? station,
    String? operatorName,
    String? operatorId,
    String? installationId,
    String? terminalLabel,
  }) async {
    final stationId = '${body['cash_station'] ?? ''}';
    // Abrir caixa sem estação criava a sessão com `cash_station: null`: ela
    // não pertencia a gaveta nenhuma, e a próxima abertura legítima era
    // recusada por conflito com essa sessão fantasma.
    if (stationId.isEmpty) {
      throw const ApiException(
        'Selecione o caixa que será aberto.',
        statusCode: 400,
      );
    }

    // Pre-checagem so para produzir a mensagem certa (quem, de onde, desde
    // quando). Quem realmente decide e o guard, dentro da transacao.
    final occupied = await occupying(stationId, restaurantId: restaurantId);
    if (occupied != null) {
      throw CashSessionConflict(occupiedMessage(occupied), session: occupied);
    }

    final id = LocalId.temporary();
    final now = DateTime.now().toUtc().toIso8601String();
    // "cem reais" no campo virava 0,00 em silêncio, e o fechamento do dia
    // acusava uma diferença que ninguém causou.
    final opening = requireMoney(
      body['opening_amount'],
      field: 'opening_amount',
      label: 'o valor de abertura',
      padrao: 0,
    );
    final record = await saveLocal(
      {
        'id': id,
        'restaurant': restaurantId,
        'cash_station': body['cash_station'],
        'cash_station_name': station?['name'],
        'status': CashSessionStatus.open,
        'opening_amount': opening.toStringAsFixed(2),
        'expected_amount': opening.toStringAsFixed(2),
        'current_balance': opening.toStringAsFixed(2),
        'notes': body['notes'] ?? '',
        // Espelha o campo herdado do backend, mas com o nome REAL quando ele
        // é conhecido. VAZIO quando não é: repetir aqui o padrão do model
        // (`"PDV principal"`) plantava, no próprio terminal, o nome que a tela
        // depois exibiria como se fosse o caixa dele. Quem resolve o rótulo é
        // [stationLabelOf], que sabe cair para o nome do terminal.
        'station': body['station'] ?? station?['name'] ?? '',
        'device_identifier': installationId ?? body['device_identifier'] ?? '',
        // Dono da sessao: operador + instalacao. E o par que `current` e as
        // movimentacoes conferem depois.
        'opened_by': operatorId ?? '',
        'opened_by_name': operatorName ?? '',
        'opened_terminal_installation_id': installationId ?? '',
        'opened_terminal_label': terminalLabel ?? '',
        'opened_at': now,
        'created_at': now,
        'updated_at': now,
        'movements': const <Map<String, dynamic>>[],
      },
      operation: SyncOperation.create,
      method: 'POST',
      path: '/cash-register/open/',
      requestBody: {...body, 'client_cash_register_id': id},
      id: id,
      guard: (tx) => _assertStationIsFree(tx, stationId),
    );
    return record.toApiJson();
  }

  /// Nenhuma outra sessao nao finalizada pode existir para este caixa.
  ///
  /// Resolvido em SQL sobre `parent_id`/`status` (ver o descritor de
  /// `cash_session`), porque so assim a leitura acontece dentro da mesma
  /// transacao da escrita.
  Future<void> _assertStationIsFree(
    SqliteWriteContext tx,
    String stationId,
  ) async {
    if (stationId.isEmpty) return;
    final rows = await tx.getAll(
      '''
      SELECT entity_id, status FROM entities
      WHERE scope = ? AND entity_type = ? AND parent_id = ? AND deleted_at IS NULL
      ''',
      [scope, type, stationId],
    );
    for (final row in rows) {
      if (!CashSessionStatus.isFinished(row['status'])) {
        throw const CashSessionConflict(
          'Este caixa ja possui uma sessao em andamento. '
          'Finalize a sessao ou solicite uma transferencia gerencial.',
        );
      }
    }
  }

  /// Confere o dono antes de mexer no dinheiro de uma sessao.
  Map<String, dynamic> _assertOwner(
    Map<String, dynamic> session, {
    String? operatorId,
    String? installationId,
  }) {
    if (_belongsTo(
      session,
      operatorId: operatorId,
      installationId: installationId,
    )) {
      return session;
    }
    throw CashSessionConflict(
      occupiedMessage(session),
      session: session,
      code: 'cash_session_forbidden',
    );
  }

  Future<Map<String, dynamic>> close(
    String id, {
    required Map<String, dynamic> body,
    String? operatorId,
    String? installationId,
  }) async {
    final session = await read(id);
    if (session == null) {
      throw StateError('Sessão de caixa $id não existe localmente.');
    }
    _assertOwner(
      session.payload,
      operatorId: operatorId,
      installationId: installationId,
    );
    // O valor conferido na gaveta é o que fecha o dia: ausente ou ilegível,
    // ele registrava zero e transformava o caixa inteiro em diferença.
    final actual = requireMoney(
      body['actual_amount'],
      field: 'actual_amount',
      label: 'o valor conferido na gaveta',
    );
    // Tudo em centavos inteiros, como o backend (`Decimal`) e como o
    // fechamento do pedido já faziam. Era o único lugar com dinheiro em
    // `double`: a tolerância de meio centavo escondia o erro de arredondamento
    // da soma, e o "bateu" daqui podia divergir do servidor por um centavo.
    final actualCents = DecimalMoney.minorUnits(actual.toStringAsFixed(2));
    final expectedCents = _drawerCents(session.payload);
    final differenceCents = actualCents - expectedCents;
    final record = await saveLocal(
      {
        ...session.payload,
        'status': differenceCents == 0
            ? CashSessionStatus.closed
            : CashSessionStatus.closedWithDifference,
        'actual_amount': DecimalMoney.format(actualCents),
        'expected_amount': DecimalMoney.format(expectedCents),
        'difference_amount': DecimalMoney.format(differenceCents),
        'closing_notes': body['notes'] ?? '',
        'closed_at': DateTime.now().toUtc().toIso8601String(),
      },
      operation: SyncOperation.update,
      method: 'POST',
      path: '/cash-register/$id/close/',
      requestBody: body,
      id: id,
    );
    return record.toApiJson();
  }

  /// Sangria (`withdrawal`) e suprimento (`supply`) — §15 e §30.
  Future<Map<String, dynamic>> registerMovement(
    String id, {
    required String movementType,
    required Map<String, dynamic> body,
    String? operatorId,
    String? installationId,
  }) async {
    final session = await read(id);
    if (session == null) {
      throw StateError('Sessão de caixa $id não existe localmente.');
    }
    _assertOwner(
      session.payload,
      operatorId: operatorId,
      installationId: installationId,
    );
    final movementId = LocalId.temporary();
    final amount = requireMoney(
      body['amount'],
      field: 'amount',
      label: 'o valor da movimentação',
    );
    // Nasce PENDENTE, como no servidor (`create_cash_movement` exige aprovação
    // para sangria e suprimento). Antes nascia sem situação — e "sem situação"
    // contava como aprovado no saldo local: a gaveta da tela descia na hora,
    // enquanto o servidor, no replay, só a desceria depois da aprovação. Um
    // fechamento feito offline batia certinho aqui e chegava lá com uma
    // diferença fantasma do valor da sangria, sem ninguém entender de onde.
    final movement = {
      'id': movementId,
      'cash_register': id,
      'movement_type': movementType,
      'amount': amount.toStringAsFixed(2),
      'reason': body['reason'] ?? '',
      'destination': body['destination'] ?? body['source'] ?? '',
      'status': 'pending',
      'created_at': DateTime.now().toUtc().toIso8601String(),
      '_offline_pending': true,
    };
    final movements = [..._movementsOf(session.payload), movement];
    final updated = {
      ...session.payload,
      'movements': movements,
    };
    final record = await saveLocal(
      {
        ...updated,
        'current_balance': _drawerAmountText(updated),
        'expected_amount': _drawerAmountText(updated),
      },
      operation: SyncOperation.update,
      method: 'POST',
      path: '/cash-register/$id/${movementType == 'supply' ? 'supply' : 'withdrawal'}/',
      requestBody: {...body, 'client_movement_id': movementId},
      id: id,
    );
    // A resposta é o MOVIMENTO, não a sessão: é o que o servidor devolve
    // (`CashMovementSerializer`), e é o `status == 'pending'` dele que faz a
    // tela abrir a autorização. Devolvendo a sessão, a tela lia `status` da
    // sessão ("open"), nunca pedia autorização, e o `approve` — se viesse —
    // apontaria para o id errado.
    return {...movement, '_session': record.toApiJson()};
  }

  /// Autoriza uma divergência de caixa ou uma movimentação pendente.
  ///
  /// A verificação da senha de ações do caixa é **local**: o hash PBKDF2 do
  /// restaurante é sincronizado e guardado no cofre do sistema
  /// (`CashAuthRepository`), justamente para isto. Sem esta operação local, um
  /// caixa que fechasse com diferença ficava travado até a internet voltar —
  /// com o operador impedido de encerrar o turno.
  ///
  /// A senha **não** entra na fila. O que sobe é a autorização; o backend
  /// revalida com a senha que o operador digitar quando a tela de revisão for
  /// aberta, ou aceita a operação de um gerente autenticado. Guardar a senha
  /// em texto no banco local seria pior do que a espera que ela evita.
  Future<Map<String, dynamic>> approve(
    String id, {
    required Map<String, dynamic> body,
    String? movementId,
    String? approverName,
  }) async {
    final session = await read(id);
    if (session == null) {
      throw StateError('Sessão de caixa $id não existe localmente.');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final reason = '${body['reason'] ?? ''}';

    if (movementId != null && movementId.isNotEmpty) {
      final movements = _movementsOf(session.payload)
          .map(
            (movement) => '${movement['id']}' == movementId
                ? {
                    ...movement,
                    'status': 'approved',
                    'approved_at': now,
                    'authorized_by_name': approverName ?? '',
                    'manager_reason': reason,
                  }
                : movement,
          )
          .toList();
      // Aprovado, o movimento passa a contar: o saldo esperado e o da gaveta
      // são refeitos aqui, como na criação. Sem isto a aprovação mudava a
      // situação do movimento e deixava `expected_amount` congelado no valor
      // de antes — o fechamento apontava diferença num turno certo.
      final updated = {...session.payload, 'movements': movements};
      final record = await saveLocal(
        {
          ...updated,
          'current_balance': _drawerAmountText(updated),
          'expected_amount': _drawerAmountText(updated),
        },
        operation: SyncOperation.update,
        method: 'POST',
        path: '/cash-register/$id/approve/',
        requestBody: {...body, 'movement': movementId},
        id: id,
      );
      return record.toApiJson();
    }

    // Divergência da própria sessão: o estado final é o mesmo que o backend
    // aplica — volta a abrir quando a pendência era a abertura, ou fecha com
    // diferença registrada.
    final pending = '${session.payload['pending_operation'] ?? ''}';
    final record = await saveLocal(
      {
        ...session.payload,
        'status': pending == 'opening'
            ? CashSessionStatus.open
            : CashSessionStatus.closedWithDifference,
        'pending_operation': null,
        'approved_at': now,
        'approval_reason': reason,
        'approved_by_name': approverName ?? '',
        if (pending != 'opening') 'closed_at': now,
      },
      operation: SyncOperation.update,
      method: 'POST',
      path: '/cash-register/$id/approve/',
      requestBody: body,
      id: id,
    );
    return record.toApiJson();
  }

  /// Lança na gaveta deste terminal um recebimento em dinheiro.
  ///
  /// O movimento equivalente nasce no servidor junto do pagamento
  /// (`register_payment`), mas só chega aqui na leitura seguinte da sessão — e
  /// até lá o operador via o caixa parado logo depois de receber em dinheiro.
  ///
  /// O lançamento local usa o id do PRÓPRIO pagamento. É o que faz ele sumir
  /// sozinho na hora certa: quando a fila entrega o recebimento,
  /// `replaceReference` troca esse id pelo definitivo, o movimento deixa de
  /// ser temporário, e a cópia seguinte do servidor — que já traz o movimento
  /// de verdade — passa a valer sem somar o mesmo dinheiro duas vezes.
  Future<void> registerLocalSale(
    String sessionId, {
    required String paymentId,
    required double amount,
    String reason = '',
  }) async {
    if (sessionId.isEmpty || paymentId.isEmpty || amount <= 0) return;
    final session = await read(sessionId);
    if (session == null) return;
    final movements = _movementsOf(session.payload);
    if (movements.any((movement) => '${movement['id']}' == paymentId)) return;
    movements.add({
      'id': paymentId,
      'cash_register': sessionId,
      'payment': paymentId,
      'movement_type': 'sale',
      'amount': amount.toStringAsFixed(2),
      'reason': reason,
      'status': 'approved',
      'created_at': DateTime.now().toUtc().toIso8601String(),
      '_offline_pending': true,
    });
    await _saveWithBalance(session.payload, movements);
  }

  /// Registra na gaveta o TROCO de um recebimento que não entrou nela.
  ///
  /// O troco sai sempre em espécie. Num recebimento em dinheiro isso já está
  /// embutido: entram R$ 50, voltam R$ 9,32, e o lançamento de venda é o
  /// líquido (R$ 40,68). Num cartão ou PIX com troco, porém, NADA entrou na
  /// gaveta e mesmo assim R$ 9,32 saíram dela — sem este lançamento, a
  /// conferência do fechamento acusaria uma falta que ninguém explicaria.
  ///
  /// Espelha o `CashMovement` de retirada que o servidor cria junto do
  /// pagamento, e some do mesmo jeito que [registerLocalSale]: o id é o do
  /// pagamento, então quando a fila entrega o recebimento a cópia do servidor
  /// passa a valer sem contar o mesmo dinheiro duas vezes.
  Future<void> registerLocalChange(
    String sessionId, {
    required String paymentId,
    required double amount,
    String reason = '',
  }) async {
    if (sessionId.isEmpty || paymentId.isEmpty || amount <= 0) return;
    final session = await read(sessionId);
    if (session == null) return;
    final movements = _movementsOf(session.payload);
    if (movements.any((movement) => '${movement['id']}' == paymentId)) return;
    movements.add({
      'id': paymentId,
      'cash_register': sessionId,
      'payment': paymentId,
      // `_signedCents` já lê `withdrawal` como saída.
      'movement_type': 'withdrawal',
      'amount': amount.toStringAsFixed(2),
      'reason': reason,
      'status': 'approved',
      'created_at': DateTime.now().toUtc().toIso8601String(),
      '_offline_pending': true,
    });
    await _saveWithBalance(session.payload, movements);
  }

  /// Desfaz o lançamento de um recebimento removido antes de subir.
  Future<void> removeLocalSale(
    String sessionId, {
    required String paymentId,
  }) async {
    if (sessionId.isEmpty || paymentId.isEmpty) return;
    final session = await read(sessionId);
    if (session == null) return;
    final movements = _movementsOf(
      session.payload,
    ).where((movement) => '${movement['id']}' != paymentId).toList();
    await _saveWithBalance(session.payload, movements);
  }

  /// Grava a sessão com o saldo recalculado, sem enfileirar nada.
  ///
  /// O dinheiro já está na fila pela operação que o gerou (o `pay` do pedido,
  /// a sangria do caixa); repetir a operação aqui a lançaria duas vezes.
  Future<void> _saveWithBalance(
    Map<String, dynamic> session,
    List<Map<String, dynamic>> movements,
  ) async {
    final updated = {...session, 'movements': movements};
    await saveLocalEffect({
      ...updated,
      'current_balance': _drawerAmountText(updated),
      'expected_amount': _drawerAmountText(updated),
    });
  }

  /// Mantém na tela o que este terminal lançou e o servidor ainda não viu.
  ///
  /// Sem isto, qualquer leitura da sessão apagava a sangria e o recebimento em
  /// dinheiro que ainda estavam na fila: o saldo voltava atrás sozinho e só se
  /// corrigia quando a operação subia.
  @override
  Future<EntityRecord?> applyRemote(
    Map<String, dynamic> payload, {
    bool overwriteLocalChanges = false,
    String? ignoreQueuedOperationId,
  }) async {
    final stored = await read('${payload['id'] ?? ''}', includeDeleted: true);
    final pending = stored == null
        ? const <Map<String, dynamic>>[]
        : _movementsOf(stored.payload)
              .where((movement) => LocalId.isTemporary('${movement['id']}'))
              .toList();
    if (pending.isEmpty) {
      return super.applyRemote(
        payload,
        overwriteLocalChanges: overwriteLocalChanges,
        ignoreQueuedOperationId: ignoreQueuedOperationId,
      );
    }
    final merged = {
      ...payload,
      'movements': [..._movementsOf(payload), ...pending],
    };
    return super.applyRemote(
      {
        ...merged,
        'current_balance': _drawerAmountText(merged),
        'expected_amount': _drawerAmountText(merged),
      },
      overwriteLocalChanges: overwriteLocalChanges,
      ignoreQueuedOperationId: ignoreQueuedOperationId,
    );
  }

  /// Dinheiro na gaveta, na mesma conta do backend.
  ///
  /// `current_balance` (serializer) e `expected_amount` (fechamento) saem os
  /// dois de `movements(status=approved).sum()`: uma soma só, com o sinal que
  /// cada movimento carrega. A conta anterior somava um `cash_sales_amount`
  /// que a API nunca enviou e ainda invertia o sinal de tudo que não fosse
  /// suprimento — um recebimento em dinheiro DIMINUÍA o esperado do caixa.
  static int _drawerCents(Map<String, dynamic> session) {
    var total = _approvedMovements(session).fold<int>(
      0,
      (sum, movement) => sum + _signedCents(movement),
    );
    // Enquanto a sessão só existe aqui não há movimento de abertura — o valor
    // contado está em `opening_amount`. Depois de subir ele vira um movimento
    // `opening`, e somar os dois contaria o troco inicial duas vezes.
    final hasOpening = _approvedMovements(
      session,
    ).any((movement) => '${movement['movement_type']}' == 'opening');
    if (!hasOpening) total += DecimalMoney.minorUnits(session['opening_amount']);
    return total;
  }

  /// O saldo já formatado com duas casas — o que os campos da sessão guardam.
  static String _drawerAmountText(Map<String, dynamic> session) =>
      DecimalMoney.format(_drawerCents(session));

  /// Sangria e estorno saem da gaveta.
  ///
  /// O backend já grava a sangria negativa (`register_cash_movement`); um
  /// movimento criado aqui nasce positivo. Normalizar na leitura aceita as
  /// duas origens sem reescrever o que já está gravado.
  static int _signedCents(Map<String, dynamic> movement) {
    final amount = DecimalMoney.minorUnits(movement['amount']).abs();
    return switch ('${movement['movement_type']}') {
      'withdrawal' || 'refund' => -amount,
      _ => amount,
    };
  }

  /// Só o que ainda conta como dinheiro — a MESMA regra do servidor.
  ///
  /// O backend filtra `status = 'approved'`. Sangria e suprimento nascem
  /// pendentes nos dois lados e só entram no saldo depois da autorização
  /// (gerente ou senha de ações do caixa, que funciona sem internet). Um
  /// movimento sem situação nenhuma é o da abertura ou o que veio de uma
  /// versão anterior, e continua contando.
  static List<Map<String, dynamic>> _approvedMovements(
    Map<String, dynamic> session,
  ) => _movementsOf(session).where((movement) {
    final status = '${movement['status'] ?? 'approved'}';
    return status == 'approved' || status.isEmpty;
  }).toList();

  static List<Map<String, dynamic>> _movementsOf(Map<String, dynamic> session) =>
      (session['movements'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
}
