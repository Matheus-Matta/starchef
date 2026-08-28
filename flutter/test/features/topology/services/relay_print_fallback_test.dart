import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';
import 'package:starchef_pdv/features/devices/services/local_device_agent.dart';
import 'package:starchef_pdv/features/topology/services/relay_print_fallback.dart';

const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEifQ.'
    'assinatura-irrelevante-no-teste';

const _scope = 'starchef.test|acc-1:authenticated';

/// **Quem imprime em nome de quem não tem impressora.**
///
/// O app do garçom manda o pedido para o Caixa Principal e não imprime nada
/// por conta própria — ele nem tem impressora. Sem este responsável, um
/// pedido enviado à cozinha (ou um item cancelado em produção) pelo celular,
/// bem na hora em que o Principal está sem internet, ficava só na fila: a
/// cozinha nunca ficava sabendo. Um Caixa Secundário continua se resolvendo
/// sozinho (`home_page.dart`) — aqui só entra quando não veio `offline_printed`
/// já marcado, exatamente a mesma trava usada em toda a impressão offline
/// deste projeto.
void main() {
  late Directory directory;
  var contador = 0;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp(
      'starchef-relay-print',
    );
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

  Future<
    ({
      ApiClient api,
      OfflineFirstGateway gateway,
      PdvDatabase database,
      LocalDeviceAgent deviceAgent,
    })
  >
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
    final api = ApiClient(baseUrl: 'http://starchef.test/api/v1', client: transport);
    api.attachLocalStore(
      gateway: gateway,
      syncService: SyncService(gateway: gateway, transport: api.syncTransport),
    );
    gateway.bindSession(scope: _scope, restaurantId: 'rest-1');

    await gateway.repository(EntityCatalog.printer).applyRemoteList([
      {
        'id': 'imp-1',
        'name': 'Cozinha',
        'restaurant': 'rest-1',
        'sector': 'cozinha',
        'sector_name': 'Cozinha',
        'is_active': true,
        'connection_type': 'usb',
      },
    ]);
    await gateway.recordSync(EntityCatalog.printer);
    await gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'X-Tudo',
        'restaurant': 'rest-1',
        'sector': 'cozinha',
      },
    ]);
    await gateway.recordSync(EntityCatalog.product);

    final deviceAgent = LocalDeviceAgent(api: api);
    addTearDown(deviceAgent.stop);
    // Síncrono: só depois disso `ensurePrinters()` sabe de qual restaurante
    // consultar (o mesmo requisito de `deviceAgent.start` em home_page.dart).
    deviceAgent.start(token: _token, restaurantId: 'rest-1');

    return (
      api: api,
      gateway: gateway,
      database: database,
      deviceAgent: deviceAgent,
    );
  }

  Future<void> seedOrder(
    OfflineFirstGateway gateway, {
    required List<Map<String, dynamic>> items,
  }) async {
    await gateway.repository(EntityCatalog.order).applyRemoteList([
      {
        'id': 'pedido-1',
        'sequence': 7,
        'status': 'open',
        'restaurant': 'rest-1',
        'items': items,
      },
    ]);
    await gateway.recordSync(EntityCatalog.order);
  }

  test(
    'sem internet no principal, a comanda do pedido do app sai por setor',
    () async {
      final stack = await build(
        MockClient((request) async => throw const SocketException('sem rede')),
      );
      await seedOrder(
        stack.gateway,
        items: [
          {
            'id': 'item-1',
            'product': 'prod-1',
            'product_name': 'X-Tudo',
            'status': 'pending',
            'quantity': '1',
          },
        ],
      );
      final fallback = RelayPrintFallback(
        api: stack.api,
        deviceAgent: stack.deviceAgent,
      );
      const mutation = RelayMutation(
        method: 'POST',
        path: '/orders/pedido-1/send-to-kitchen/',
        operationId: 'op-envio-1',
        body: {'client_batch_serial': 'lote-1'},
      );

      final beforeOrder = await fallback.captureBeforeState(mutation);
      expect(beforeOrder, isNotNull);

      final response = await stack.api.acceptRelayedMutation(
        mutation,
        accessToken: _token,
      );
      await fallback.afterAcceptedMutation(
        mutation: mutation,
        beforeOrder: beforeOrder,
        response: response,
      );

      final printed = await stack.gateway.printQueue.entries(scope: _scope);
      expect(printed, hasLength(1));
      expect(printed.single.jobType, 'kitchen');
      expect(printed.single.content, contains('X-Tudo'));

      final queued = await stack.gateway.queue.entries(scope: _scope);
      final op = queued.firstWhere(
        (entry) => entry.path.endsWith('/send-to-kitchen/'),
      );
      // Reivindicado: quando a fila enfim sincronizar, o backend não cria
      // outro `PrintJob` para a mesma rodada.
      expect(op.payload!['offline_printed'], isTrue);

      await stack.api.dispose();
      await stack.database.close();
    },
  );

  test(
    'com internet no principal, quem imprime é o backend — nada sai aqui',
    () async {
      final stack = await build(
        MockClient((request) async => json({'id': 'pedido-1', 'items': []})),
      );
      await seedOrder(
        stack.gateway,
        items: [
          {
            'id': 'item-1',
            'product': 'prod-1',
            'product_name': 'X-Tudo',
            'status': 'pending',
            'quantity': '1',
          },
        ],
      );
      final fallback = RelayPrintFallback(
        api: stack.api,
        deviceAgent: stack.deviceAgent,
      );
      const mutation = RelayMutation(
        method: 'POST',
        path: '/orders/pedido-1/send-to-kitchen/',
        operationId: 'op-envio-2',
        body: {'client_batch_serial': 'lote-2'},
      );

      final beforeOrder = await fallback.captureBeforeState(mutation);
      final response = await stack.api.acceptRelayedMutation(
        mutation,
        accessToken: _token,
      );
      await fallback.afterAcceptedMutation(
        mutation: mutation,
        beforeOrder: beforeOrder,
        response: response,
      );

      // A operação subiu de verdade: nenhuma comanda extra sai deste terminal.
      final printed = await stack.gateway.printQueue.entries(scope: _scope);
      expect(printed, isEmpty);

      await stack.api.dispose();
      await stack.database.close();
    },
  );

  test(
    'um Caixa Secundário que já imprimiu não é impresso de novo pelo principal',
    () async {
      final stack = await build(
        MockClient((request) async => throw const SocketException('sem rede')),
      );
      await seedOrder(
        stack.gateway,
        items: [
          {
            'id': 'item-1',
            'product': 'prod-1',
            'product_name': 'X-Tudo',
            'status': 'pending',
            'quantity': '1',
          },
        ],
      );
      final fallback = RelayPrintFallback(
        api: stack.api,
        deviceAgent: stack.deviceAgent,
      );
      // O Caixa Secundário já reivindicou e imprimiu na própria impressora
      // antes de conseguir alcançar o Principal: o corpo chega com a marca.
      const mutation = RelayMutation(
        method: 'POST',
        path: '/orders/pedido-1/send-to-kitchen/',
        operationId: 'op-envio-3',
        body: {'client_batch_serial': 'lote-3', 'offline_printed': true},
      );

      final beforeOrder = await fallback.captureBeforeState(mutation);
      final response = await stack.api.acceptRelayedMutation(
        mutation,
        accessToken: _token,
      );
      await fallback.afterAcceptedMutation(
        mutation: mutation,
        beforeOrder: beforeOrder,
        response: response,
      );

      final printed = await stack.gateway.printQueue.entries(scope: _scope);
      expect(printed, isEmpty);

      await stack.api.dispose();
      await stack.database.close();
    },
  );

  test(
    'item cancelado em produção: o cupom de cancelamento sai no setor',
    () async {
      final stack = await build(
        MockClient((request) async => throw const SocketException('sem rede')),
      );
      await seedOrder(
        stack.gateway,
        items: [
          {
            'id': 'item-1',
            'product': 'prod-1',
            'product_name': 'X-Tudo',
            'status': 'sent',
            'quantity': '1',
          },
        ],
      );
      final fallback = RelayPrintFallback(
        api: stack.api,
        deviceAgent: stack.deviceAgent,
      );
      const mutation = RelayMutation(
        method: 'DELETE',
        path: '/orders/pedido-1/items/item-1/void/',
        operationId: 'op-cancela-1',
        body: {'reason': 'Cliente desistiu'},
      );

      final beforeOrder = await fallback.captureBeforeState(mutation);
      expect(beforeOrder, isNotNull);

      final response = await stack.api.acceptRelayedMutation(
        mutation,
        accessToken: _token,
      );
      await fallback.afterAcceptedMutation(
        mutation: mutation,
        beforeOrder: beforeOrder,
        response: response,
      );

      final printed = await stack.gateway.printQueue.entries(scope: _scope);
      expect(printed, hasLength(1));
      expect(printed.single.jobType, 'kitchen_cancel');
      expect(printed.single.content, contains('CANCELAMENTO'));

      await stack.api.dispose();
      await stack.database.close();
    },
  );

  test(
    'item cancelado antes de ir para a cozinha não gera cupom nenhum',
    () async {
      final stack = await build(
        MockClient((request) async => throw const SocketException('sem rede')),
      );
      await seedOrder(
        stack.gateway,
        items: [
          {
            'id': 'item-1',
            'product': 'prod-1',
            'product_name': 'X-Tudo',
            'status': 'pending',
            'quantity': '1',
          },
        ],
      );
      final fallback = RelayPrintFallback(
        api: stack.api,
        deviceAgent: stack.deviceAgent,
      );
      const mutation = RelayMutation(
        method: 'DELETE',
        path: '/orders/pedido-1/items/item-1/void/',
        operationId: 'op-cancela-2',
        body: {'reason': 'Errei o pedido'},
      );

      final beforeOrder = await fallback.captureBeforeState(mutation);
      final response = await stack.api.acceptRelayedMutation(
        mutation,
        accessToken: _token,
      );
      await fallback.afterAcceptedMutation(
        mutation: mutation,
        beforeOrder: beforeOrder,
        response: response,
      );

      final printed = await stack.gateway.printQueue.entries(scope: _scope);
      expect(printed, isEmpty);

      await stack.api.dispose();
      await stack.database.close();
    },
  );
}
