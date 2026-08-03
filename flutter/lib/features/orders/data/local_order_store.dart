import 'dart:convert';
import 'dart:io';

import 'package:sqlite_async/sqlite_async.dart';

import '../../../core/formatters/value_formatters.dart';
import '../../../core/storage/app_paths.dart';

/// Cópia local dos pedidos, com as alterações feitas sem rede já aplicadas.
///
/// O cache do `ApiClient` guarda **respostas HTTP**. Isso basta para ler, mas
/// não para editar: incluir um item offline alterava só a memória da tela, e
/// ao sair e voltar o operador via o pedido antigo de novo — a resposta
/// guardada não conhecia a mudança.
///
/// Este store guarda o **pedido**, não a resposta. As mutações offline são
/// aplicadas aqui e os totais recalculados, então a tela mostra o mesmo antes
/// e depois de navegar. A fila de sincronização continua sendo a fonte da
/// verdade para o servidor; aqui fica o que o terminal precisa exibir enquanto
/// a rede não volta.
class LocalOrderStore {
  LocalOrderStore({File? file}) : _file = file ?? _defaultFile() {
    _database = SqliteDatabase(path: _file.path);
    _ready = _initialize();
  }

  /// Pedidos guardados por escopo; o suficiente para o movimento recente.
  static const _maximumOrders = 200;

  final File _file;
  late final SqliteDatabase _database;
  late final Future<void> _ready;
  bool _closed = false;

  static File _defaultFile() => AppPaths.dataFile('local_orders.sqlite');

  Future<void> _initialize() async {
    await _file.parent.create(recursive: true);
    final migrations = SqliteMigrations()
      ..createDatabase = SqliteMigration(1, _createSchema)
      ..add(SqliteMigration(1, _createSchema));
    await migrations.migrate(_database);
  }

  static Future<void> _createSchema(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS local_orders (
        scope TEXT NOT NULL,
        order_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        updated_at INTEGER NOT NULL,
        has_local_changes INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (scope, order_id)
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS local_orders_recent_idx
      ON local_orders(scope, updated_at DESC)
    ''');
  }

  /// Guarda a versão vinda do servidor.
  ///
  /// Itens criados offline (id `offline-...`) que o servidor ainda não conhece
  /// são preservados: eles estão na fila e sumiriam da tela até ela esvaziar,
  /// dando ao operador a impressão de que o lançamento se perdeu.
  Future<Map<String, dynamic>> saveFromServer(
    Map<String, dynamic> order, {
    required String scope,
  }) async {
    await _ready;
    final id = '${order['id'] ?? ''}';
    if (id.isEmpty) return order;

    final stored = await read(id, scope: scope);
    final pendingItems = stored == null
        ? const <Map<String, dynamic>>[]
        : _itemsOf(stored)
              .where((item) => '${item['id']}'.startsWith('offline-'))
              .toList();

    final merged = pendingItems.isEmpty
        ? Map<String, dynamic>.from(order)
        : _withItems(order, [..._itemsOf(order), ...pendingItems]);
    await _write(
      merged,
      scope: scope,
      hasLocalChanges: pendingItems.isNotEmpty,
    );
    return merged;
  }

  /// Guarda vários pedidos de uma listagem.
  Future<void> saveAllFromServer(
    List<Map<String, dynamic>> orders, {
    required String scope,
  }) async {
    for (final order in orders) {
      await saveFromServer(order, scope: scope);
    }
  }

  Future<Map<String, dynamic>?> read(
    String orderId, {
    required String scope,
  }) async {
    await _ready;
    final row = await _database.getOptional(
      'SELECT payload FROM local_orders WHERE scope = ? AND order_id = ?',
      [scope, orderId],
    );
    if (row == null) return null;
    return _decode(row['payload']);
  }

  /// Pedidos guardados, do mais recente para o mais antigo.
  Future<List<Map<String, dynamic>>> recent({
    required String scope,
    int limit = 50,
  }) async {
    await _ready;
    final rows = await _database.getAll(
      '''
      SELECT payload FROM local_orders
      WHERE scope = ?
      ORDER BY updated_at DESC
      LIMIT ?
      ''',
      [scope, limit],
    );
    return rows
        .map((row) => _decode(row['payload']))
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  /// Acrescenta um item lançado sem rede e recalcula os totais.
  Future<Map<String, dynamic>?> addItem(
    String orderId,
    Map<String, dynamic> item, {
    required String scope,
  }) async {
    final order = await read(orderId, scope: scope);
    if (order == null) return null;
    final updated = _withItems(order, [..._itemsOf(order), item]);
    await _write(updated, scope: scope, hasLocalChanges: true);
    return updated;
  }

  /// Marca um item como cancelado, do mesmo jeito que o servidor faria.
  Future<Map<String, dynamic>?> voidItem(
    String orderId,
    String itemId, {
    required String scope,
  }) async {
    final order = await read(orderId, scope: scope);
    if (order == null) return null;
    final items = _itemsOf(order)
        .map(
          (item) => '${item['id']}' == itemId
              ? {...item, 'status': 'voided'}
              : item,
        )
        .toList();
    final updated = _withItems(order, items);
    await _write(updated, scope: scope, hasLocalChanges: true);
    return updated;
  }

  /// Aplica uma mudança de estado do pedido (fechado, pago, na cozinha).
  Future<Map<String, dynamic>?> patch(
    String orderId,
    Map<String, dynamic> changes, {
    required String scope,
  }) async {
    final order = await read(orderId, scope: scope);
    if (order == null) return null;
    final updated = {...order, ...changes};
    await _write(updated, scope: scope, hasLocalChanges: true);
    return updated;
  }

  /// Troca o ID temporário pelo real depois que a fila sincroniza.
  Future<void> replaceId(
    String temporaryId,
    String realId, {
    required String scope,
  }) async {
    await _ready;
    if (temporaryId.isEmpty || realId.isEmpty) return;
    await _database.writeTransaction((tx) async {
      await tx.execute(
        '''
        UPDATE local_orders
        SET payload = replace(payload, ?, ?),
            order_id = CASE WHEN order_id = ? THEN ? ELSE order_id END
        WHERE scope = ?
        ''',
        [temporaryId, realId, temporaryId, realId, scope],
      );
    });
  }

  Future<void> remove(String orderId, {required String scope}) async {
    await _ready;
    await _database.execute(
      'DELETE FROM local_orders WHERE scope = ? AND order_id = ?',
      [scope, orderId],
    );
  }

  Future<void> _write(
    Map<String, dynamic> order, {
    required String scope,
    required bool hasLocalChanges,
  }) async {
    await _ready;
    final id = '${order['id'] ?? ''}';
    if (id.isEmpty) return;
    await _database.writeTransaction((tx) async {
      await tx.execute(
        '''
        INSERT INTO local_orders(
          scope, order_id, payload, updated_at, has_local_changes
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(scope, order_id) DO UPDATE SET
          payload = excluded.payload,
          updated_at = excluded.updated_at,
          has_local_changes = MAX(
            local_orders.has_local_changes, excluded.has_local_changes
          )
        ''',
        [
          scope,
          id,
          jsonEncode(order),
          DateTime.now().millisecondsSinceEpoch,
          hasLocalChanges ? 1 : 0,
        ],
      );
      // Mantém o banco pequeno: um PDV não precisa do histórico inteiro para
      // operar offline, e pedidos antigos raramente voltam a ser editados.
      await tx.execute(
        '''
        DELETE FROM local_orders
        WHERE scope = ? AND order_id IN (
          SELECT order_id FROM local_orders
          WHERE scope = ? AND has_local_changes = 0
          ORDER BY updated_at DESC
          LIMIT -1 OFFSET ?
        )
        ''',
        [scope, scope, _maximumOrders],
      );
    });
  }

  /// Recalcula subtotal e total a partir dos itens ativos.
  ///
  /// Taxas e desconto vêm do servidor e são preservados: o terminal não tem
  /// como recalcular a regra de serviço ou uma promoção aplicada lá.
  static Map<String, dynamic> _withItems(
    Map<String, dynamic> order,
    List<Map<String, dynamic>> items,
  ) {
    final active = items
        .where((item) => item['status'] != 'voided')
        .toList(growable: false);
    final subtotal = active.fold<double>(
      0,
      (sum, item) => sum + ValueFormatters.number(item['total_price']),
    );
    final serviceFee = ValueFormatters.number(order['service_fee']);
    final deliveryFee = ValueFormatters.number(order['delivery_fee']);
    final discount = ValueFormatters.number(order['discount']);
    final total = subtotal + serviceFee + deliveryFee - discount;
    return {
      ...order,
      'items': items,
      'subtotal': subtotal.toStringAsFixed(2),
      'total': (total < 0 ? 0.0 : total).toStringAsFixed(2),
    };
  }

  static List<Map<String, dynamic>> _itemsOf(Map<String, dynamic> order) =>
      (order['items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();

  static Map<String, dynamic>? _decode(Object? raw) {
    if (raw is! String || raw.isEmpty) return null;
    final decoded = jsonDecode(raw);
    return decoded is Map ? Map<String, dynamic>.from(decoded) : null;
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    await _ready;
    await _database.close();
  }
}
