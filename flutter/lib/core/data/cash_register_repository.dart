import 'package:sqlite_async/sqlite_async.dart';

import '../formatters/value_formatters.dart';
import '../network/api_exception.dart';
import 'cash_session_status.dart';
import 'entity_catalog.dart';
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
  /// Quando a sessão não registra dono (base antiga), não há o que comparar e
  /// ela é aceita; quando registra, os dois lados precisam bater.
  static bool _belongsTo(
    Map<String, dynamic> session, {
    String? operatorId,
    String? installationId,
  }) {
    final owner = '${session['opened_by'] ?? ''}';
    if (owner.isNotEmpty && (operatorId ?? '').isNotEmpty && owner != operatorId) {
      return false;
    }
    final terminal = '${session['opened_terminal_installation_id'] ?? ''}';
    if (terminal.isNotEmpty && terminal != (installationId ?? '')) return false;
    return true;
  }

  /// Mensagem de bloqueio, no mesmo formato do backend.
  static String occupiedMessage(Map<String, dynamic> session) {
    final station = '${session['cash_station_name'] ?? session['station'] ?? 'caixa'}';
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

    // Pre-checagem so para produzir a mensagem certa (quem, de onde, desde
    // quando). Quem realmente decide e o guard, dentro da transacao.
    final occupied = await occupying(stationId, restaurantId: restaurantId);
    if (occupied != null) {
      throw CashSessionConflict(occupiedMessage(occupied), session: occupied);
    }

    final id = LocalId.temporary();
    final now = DateTime.now().toUtc().toIso8601String();
    final opening = ValueFormatters.number(body['opening_amount']);
    final record = await saveLocal(
      {
        'id': id,
        'restaurant': restaurantId,
        'cash_station': body['cash_station'],
        'cash_station_name': station?['name'],
        'status': CashSessionStatus.open,
        'opening_amount': opening.toStringAsFixed(2),
        'expected_amount': opening.toStringAsFixed(2),
        'notes': body['notes'] ?? '',
        'station': body['station'] ?? 'PDV principal',
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
    final actual = ValueFormatters.number(body['actual_amount']);
    final expected = _expectedAmount(session.payload);
    final difference = actual - expected;
    final record = await saveLocal(
      {
        ...session.payload,
        'status': difference.abs() < 0.005
            ? CashSessionStatus.closed
            : CashSessionStatus.closedWithDifference,
        'actual_amount': actual.toStringAsFixed(2),
        'expected_amount': expected.toStringAsFixed(2),
        'difference_amount': difference.toStringAsFixed(2),
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
    final amount = ValueFormatters.number(body['amount']);
    final movement = {
      'id': movementId,
      'cash_register': id,
      'movement_type': movementType,
      'amount': amount.toStringAsFixed(2),
      'reason': body['reason'] ?? '',
      'destination': body['destination'] ?? body['source'] ?? '',
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
        'expected_amount': _expectedAmount(updated).toStringAsFixed(2),
      },
      operation: SyncOperation.update,
      method: 'POST',
      path: '/cash-register/$id/${movementType == 'supply' ? 'supply' : 'withdrawal'}/',
      requestBody: {...body, 'client_movement_id': movementId},
      id: id,
    );
    return {...record.toApiJson(), '_created_movement': movement};
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
      final record = await saveLocal(
        {...session.payload, 'movements': movements},
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

  /// Saldo previsto: abertura + suprimentos - sangrias + recebimentos em
  /// dinheiro já informados pelo servidor.
  static double _expectedAmount(Map<String, dynamic> session) {
    var total = ValueFormatters.number(session['opening_amount']);
    total += ValueFormatters.number(session['cash_sales_amount']);
    for (final movement in _movementsOf(session)) {
      final amount = ValueFormatters.number(movement['amount']);
      total += '${movement['movement_type']}' == 'supply' ? amount : -amount;
    }
    return total;
  }

  static List<Map<String, dynamic>> _movementsOf(Map<String, dynamic> session) =>
      (session['movements'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
}
