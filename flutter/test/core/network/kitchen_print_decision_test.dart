import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';

const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEifQ.'
    'assinatura-irrelevante-no-teste';

/// **Quem imprime a comanda de cozinha.**
///
/// É a decisão mais perigosa do PDV offline-first, porque os dois erros
/// possíveis são graves: imprimir aqui uma comanda que o backend também vai
/// imprimir (duas comandas para a mesma rodada) ou não imprimir nenhuma das
/// duas (a cozinha não fica sabendo do pedido).
///
/// A regra é factual, não um palpite sobre a conexão: **a operação chegou ao
/// servidor?** Se chegou, o backend cria o `PrintJob` e o agente imprime. Se
/// continua na fila, quem imprime é este terminal — e ele reivindica a
/// impressão marcando o corpo enfileirado ANTES de mandar papel.
void main() {
  late Directory directory;
  var contador = 0;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-kitchen-print');
  });

  tearDown(() async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  http.Response json(Object body, [int status = 200]) => http.Response(
    jsonEncode(body),
    status,
    headers: {'content-type': 'application/json'},
  );

  Future<({ApiClient api, OfflineFirstGateway gateway, PdvDatabase database})>
  build(http.Client transport) async {
    contador += 1;
    final sep = Platform.pathSeparator;
    final database = PdvDatabase(
      file: File('${directory.path}${sep}pdv-$contador.sqlite'),
    );
    await database.ready;
    final gateway = OfflineFirstGateway(
      database: database,
      queue: SyncQueueService(database: database),
      fiscalQueue: FiscalQueueService(database: database),
    );
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: transport,
      offlineStore: OfflineStore(
        file: File('${directory.path}${sep}legacy-$contador.sqlite'),
      ),
    );
    api.attachLocalStore(
      gateway: gateway,
      syncService: SyncService(gateway: gateway, transport: api.syncTransport),
    );
    return (api: api, gateway: gateway, database: database);
  }

  Future<String> abrirPedido(ApiClient api) async {
    final created = await api.post(
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
      accessToken: _token,
    );
    return '${created['id']}';
  }

  test('com a rede de pé a operação sobe e o backend imprime', () async {
    final stack = await build(
      MockClient((request) async => json({'id': 'pedido-real', 'items': []})),
    );
    final orderId = await abrirPedido(stack.api);

    final response = await stack.api.post(
      '/orders/$orderId/send-to-kitchen/',
      body: {'client_batch_serial': 'lote-1'},
      accessToken: _token,
    );
    final operationId = '${response['_sync_operation_id']}';

    // Entregue: o terminal NÃO imprime, senão sairiam duas comandas.
    expect(
      await stack.api.awaitDelivery(
        operationId,
        // Folga de propósito: o que este teste afirma é que a operação SOBE,
        // não em quantos milissegundos. Com a suíte inteira disputando o
        // disco, os 3 s do padrão faziam ele falhar por carga da máquina —
        // passava sozinho e quebrava no run completo.
        timeout: const Duration(seconds: 30),
      ),
      isTrue,
    );
    // E não dá mais para reivindicar a impressão: a operação já saiu da fila.
    expect(
      await stack.api.patchQueuedBody(operationId, {'offline_printed': true}),
      isFalse,
    );

    await stack.api.dispose();
    await stack.database.close();
  });

  test('sem rede a operação fica na fila e o terminal assume a impressão', () async {
    final stack = await build(
      MockClient((request) async => throw const SocketException('sem rede')),
    );
    final orderId = await abrirPedido(stack.api);

    final response = await stack.api.post(
      '/orders/$orderId/send-to-kitchen/',
      body: {'client_batch_serial': 'lote-1'},
      accessToken: _token,
    );
    final operationId = '${response['_sync_operation_id']}';

    expect(
      await stack.api.awaitDelivery(
        operationId,
        timeout: const Duration(milliseconds: 300),
      ),
      isFalse,
    );
    // Reivindica a impressão: o corpo enfileirado passa a dizer ao backend
    // que a comanda já saiu, para ele não criar um `PrintJob` novo quando a
    // fila sincronizar.
    expect(
      await stack.api.patchQueuedBody(operationId, {'offline_printed': true}),
      isTrue,
    );

    final queued = await stack.gateway.queue.entries(
      scope: stack.gateway.scope!,
    );
    final kitchen = queued.firstWhere(
      (entry) => entry.path.endsWith('/send-to-kitchen/'),
    );
    expect(kitchen.payload!['offline_printed'], isTrue);
    expect(kitchen.payload!['client_batch_serial'], 'lote-1');

    await stack.api.dispose();
    await stack.database.close();
  });

  test('impressora falhou: a impressão volta a ser do backend', () async {
    final stack = await build(
      MockClient((request) async => throw const SocketException('sem rede')),
    );
    final orderId = await abrirPedido(stack.api);
    final response = await stack.api.post(
      '/orders/$orderId/send-to-kitchen/',
      body: {'client_batch_serial': 'lote-1'},
      accessToken: _token,
    );
    final operationId = '${response['_sync_operation_id']}';

    await stack.api.patchQueuedBody(operationId, {'offline_printed': true});
    // Não saiu papel aqui. Sem devolver a responsabilidade, a cozinha ficaria
    // sem comanda agora E quando a fila sincronizasse.
    await stack.api.patchQueuedBody(operationId, {'offline_printed': false});

    final queued = await stack.gateway.queue.entries(
      scope: stack.gateway.scope!,
    );
    final kitchen = queued.firstWhere(
      (entry) => entry.path.endsWith('/send-to-kitchen/'),
    );
    expect(kitchen.payload!['offline_printed'], isFalse);

    await stack.api.dispose();
    await stack.database.close();
  });

  test('a queda da rede chega ao indicador de conexão do PDV', () async {
    // Sem esta ponte o `syncStatus` ficava congelado em "sincronizando" com a
    // internet fora — e é ele que o cabeçalho mostra ao operador.
    final stack = await build(
      MockClient((request) async => throw const SocketException('sem rede')),
    );
    await abrirPedido(stack.api);

    await stack.api.syncService!.push();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(stack.api.syncStatus.phase, NetworkSyncPhase.offline);
    expect(stack.api.syncStatus.hasConnection, isFalse);

    await stack.api.dispose();
    await stack.database.close();
  });

  test('as rotas de impressão do backend nunca são atendidas localmente', () async {
    final stack = await build(MockClient((request) async => json({'ok': true})));
    stack.gateway.bindSession(scope: 'starchef.test|acc-1:authenticated');

    for (final path in const [
      '/print-jobs/',
      '/print-jobs/job-1/mark-printed/',
      '/print-jobs/job-1/mark-failed/',
      '/printers/impressora-1/test-connection/',
      '/orders/pedido-1/print/',
      '/invoices/nota-1/print/',
    ]) {
      expect(
        stack.gateway.handlesWrite('POST', path, const {}),
        isFalse,
        reason: path,
      );
      expect(stack.gateway.handlesRead(path), isFalse, reason: path);
    }
    // O cadastro de impressoras, ao contrário, precisa estar offline: é ele
    // que diz onde imprimir (§18).
    expect(stack.gateway.handlesRead('/printers/'), isTrue);
    // Já os modelos não são coleção de entidades — quem os guarda em disco é
    // o `PrintTemplateCache`.
    expect(stack.gateway.handlesRead('/printers/templates/'), isFalse);

    await stack.api.dispose();
    await stack.database.close();
  });
}
