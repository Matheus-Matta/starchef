import 'dart:io';

import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';

/// Núcleo local completo em um arquivo temporário, sem rede nem interface.
///
/// Os testes de arquitetura offline precisam do banco de verdade: metade do
/// que se quer garantir (transação única, FIFO, exclusão lógica, paginação)
/// só existe no SQLite. Um duplo em memória provaria o duplo, não o produto.
class TestPdvStack {
  TestPdvStack._({
    required this.directory,
    required this.database,
    required this.queue,
    required this.fiscalQueue,
    required this.gateway,
  });

  static const scope = 'starchef.test|conta-1:operador-1';

  final Directory directory;
  final PdvDatabase database;
  final SyncQueueService queue;
  final FiscalQueueService fiscalQueue;
  final OfflineFirstGateway gateway;

  static Future<TestPdvStack> create({String? restaurantId}) async {
    final directory = await Directory.systemTemp.createTemp('starchef-pdv-db');
    final database = PdvDatabase(
      file: File('${directory.path}${Platform.pathSeparator}pdv.sqlite'),
    );
    await database.ready;
    final queue = SyncQueueService(database: database);
    final fiscalQueue = FiscalQueueService(database: database);
    final gateway = OfflineFirstGateway(
      database: database,
      queue: queue,
      fiscalQueue: fiscalQueue,
    )..bindSession(scope: scope, restaurantId: restaurantId ?? 'rest-1');
    return TestPdvStack._(
      directory: directory,
      database: database,
      queue: queue,
      fiscalQueue: fiscalQueue,
      gateway: gateway,
    );
  }

  Future<void> dispose() async {
    await database.close();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  }
}

/// Uma requisição que o transporte falso recebeu.
class RecordedRequest {
  const RecordedRequest({
    required this.method,
    required this.path,
    this.query,
    this.body,
    this.idempotencyKey,
  });

  final String method;
  final String path;
  final Map<String, dynamic>? query;
  final Map<String, dynamic>? body;
  final String? idempotencyKey;
}

/// Transporte controlado pelo teste: nenhuma chamada sai da máquina.
class FakeSyncTransport implements SyncTransport {
  FakeSyncTransport({this.online = true});

  bool online;
  final List<RecordedRequest> requests = [];

  /// Resposta por rota. A chave é `MÉTODO caminho`.
  final Map<String, Object Function(RecordedRequest)> handlers = {};

  /// Resposta padrão quando nenhum handler casa.
  Object Function(RecordedRequest)? fallback;

  @override
  Future<bool> ping() async => online;

  @override
  Future<Map<String, dynamic>> send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? idempotencyKey,
  }) async {
    final request = RecordedRequest(
      method: method,
      path: path,
      query: query,
      body: body,
      idempotencyKey: idempotencyKey,
    );
    requests.add(request);
    if (!online) {
      throw const TransientSyncFailure('Sem conexão com o servidor.');
    }
    final handler = handlers['$method $path'] ?? fallback;
    if (handler == null) {
      return <String, dynamic>{'ok': true};
    }
    final result = handler(request);
    if (result is Map<String, dynamic>) return result;
    if (result is Exception) throw result;
    throw StateError('Resposta de teste inválida para $method $path.');
  }
}

/// Página no formato do DRF, para exercitar a paginação de 20 em 20 (§13).
Map<String, dynamic> paginated(
  List<Map<String, dynamic>> results, {
  required int count,
  String? next,
}) => {
  'count': count,
  'next': next,
  'previous': null,
  'results': results,
};
