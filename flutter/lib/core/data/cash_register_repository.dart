import '../formatters/value_formatters.dart';
import 'entity_catalog.dart';
import 'entity_repository.dart';
import 'local_id.dart';
import 'sync_operation.dart';

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

  /// Sessão em andamento do restaurante, se houver.
  ///
  /// Espelha `/cash-register/current/`: a mais recente que não esteja
  /// fechada nem cancelada.
  Future<Map<String, dynamic>?> current({String? restaurantId}) async {
    final page = await list(
      query: {
        'restaurant': ?restaurantId,
        'page_size': 50,
      },
    );
    for (final session in page.results) {
      const finished = {'closed', 'closed_difference', 'cancelled'};
      if (!finished.contains('${session['status']}')) return session;
    }
    return null;
  }

  Future<Map<String, dynamic>> open({
    required Map<String, dynamic> body,
    required String? restaurantId,
    Map<String, dynamic>? station,
    String? operatorName,
  }) async {
    final id = LocalId.temporary();
    final now = DateTime.now().toUtc().toIso8601String();
    final opening = ValueFormatters.number(body['opening_amount']);
    final record = await saveLocal(
      {
        'id': id,
        'restaurant': restaurantId,
        'cash_station': body['cash_station'],
        'cash_station_name': station?['name'],
        'status': 'open',
        'opening_amount': opening.toStringAsFixed(2),
        'expected_amount': opening.toStringAsFixed(2),
        'notes': body['notes'] ?? '',
        'station': body['station'] ?? 'PDV principal',
        'device_identifier': body['device_identifier'] ?? '',
        'opened_by_name': operatorName ?? '',
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
    );
    return record.toApiJson();
  }

  Future<Map<String, dynamic>> close(
    String id, {
    required Map<String, dynamic> body,
  }) async {
    final session = await read(id);
    if (session == null) {
      throw StateError('Sessão de caixa $id não existe localmente.');
    }
    final actual = ValueFormatters.number(body['actual_amount']);
    final expected = _expectedAmount(session.payload);
    final difference = actual - expected;
    final record = await saveLocal(
      {
        ...session.payload,
        'status': difference.abs() < 0.005 ? 'closed' : 'closed_difference',
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
  }) async {
    final session = await read(id);
    if (session == null) {
      throw StateError('Sessão de caixa $id não existe localmente.');
    }
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
        'status': pending == 'opening' ? 'open' : 'closed_difference',
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
