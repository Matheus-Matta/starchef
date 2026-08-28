import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/features/topology/data/local_topology_store.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

/// Token com claim de conta, para o escopo do banco local ficar estável.
const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiY29udGEtMSJ9.'
    'assinatura-irrelevante-no-teste';

/// O Caixa Principal como **servidor local do restaurante** (§10).
///
/// Um aparelho na rede pede `GET /local/orders` e recebe os pedidos do SQLite
/// do principal — sem internet, sem nuvem, sem banco compartilhado. É o que
/// garante uma única base operacional para o salão inteiro (§8, §9).
void main() {
  const accountId = 'conta-1';
  const restaurantId = 'restaurante-1';

  late Directory temporaryDirectory;
  late LocalTopologyService service;
  late ApiClient api;
  late PdvDatabase database;
  late OfflineFirstGateway gateway;
  late String secret;
  late int port;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'starchef-local-api-',
    );
    final sep = Platform.pathSeparator;
    database = PdvDatabase(
      file: File('${temporaryDirectory.path}${sep}pdv.sqlite'),
    );
    await database.ready;
    gateway = OfflineFirstGateway(
      database: database,
      queue: SyncQueueService(database: database),
      fiscalQueue: FiscalQueueService(database: database),
    );
    // Sem rede alguma: o principal responde só do que tem gravado.
    api = ApiClient(baseUrl: 'http://127.0.0.1:9/api/v1');
    api.attachLocalStore(gateway: gateway);
    gateway.bindSession(
      scope: '127.0.0.1:9|conta-1:authenticated',
      restaurantId: restaurantId,
    );
    await gateway.repository(EntityCatalog.order).applyRemoteList([
      {
        'id': 'pedido-1',
        'sequence': 10,
        'status': 'open',
        'restaurant': restaurantId,
        'items': const [],
      },
    ]);
    await gateway.recordSync(EntityCatalog.order);
    await gateway.repository(EntityCatalog.printer).applyRemoteList([
      {
        'id': 'impressora-1',
        'name': 'Cozinha',
        'restaurant': restaurantId,
        'connection_type': 'usb',
      },
    ]);
    await gateway.recordSync(EntityCatalog.printer);

    secret = LocalTopologyStore.generatePairingSecret();
    service = LocalTopologyService(
      api: api,
      accessToken: _token,
      accountId: accountId,
      actorId: 'operador-do-caixa',
      restaurantId: restaurantId,
      store: LocalTopologyStore(
        file: File('${temporaryDirectory.path}${sep}topology.sqlite'),
        secretStorage: _MemorySecretStorage(),
      ),
    );
    // Entre descobrir uma porta livre e abri-la existe uma janela em que outro
    // teste rodando em paralelo pode tomá-la. Tentar de novo em outra porta é
    // mais honesto do que aceitar um teste que falha de vez em quando.
    for (var tentativa = 0; tentativa < 5; tentativa++) {
      port = await _freePort();
      await service.reconfigure(
        LocalTopologyConfig(
          mode: LocalTopologyMode.principal,
          nodeId: 'caixa-principal',
          port: port,
          pairingSecret: secret,
          trustedNetworkAcknowledged: true,
        ),
      );
      if (service.status.phase == LocalTopologyPhase.principalReady) break;
    }
    expect(service.status.phase, LocalTopologyPhase.principalReady);
  });

  tearDown(() async {
    await service.shutdown();
    await api.dispose();
    await database.close();
    await _deleteTemporaryDirectory(temporaryDirectory);
  });

  Future<({int status, Map<String, dynamic> body})> call(
    String method,
    String path, {
    Map<String, dynamic>? body,
    String nonce = 'nonce-do-aparelho-1',
  }) async {
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
    final encodedBody = body == null ? '' : jsonEncode(body);
    final signature = LocalRelayAuthenticator.signature(
      secret: secret,
      method: method,
      path: path,
      timestamp: timestamp,
      nonce: nonce,
      account: accountId,
      actor: 'garcom-maria',
      restaurant: restaurantId,
      nodeId: 'celular-do-garcom',
      body: encodedBody,
    );
    final client = HttpClient();
    try {
      final request = await client.openUrl(
        method,
        Uri.parse('http://127.0.0.1:$port$path'),
      );
      request.headers
        ..set('x-starchef-timestamp', '$timestamp')
        ..set('x-starchef-nonce', nonce)
        ..set('x-starchef-node', 'celular-do-garcom')
        ..set('x-starchef-account', accountId)
        ..set('x-starchef-actor', 'garcom-maria')
        ..set('x-starchef-restaurant', restaurantId)
        ..set('x-starchef-signature', signature);
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(encodedBody);
      }
      final response = await request.close();
      final raw = await utf8.decoder.bind(response).join();
      final decoded = raw.isEmpty ? const {} : jsonDecode(raw) as Map;
      return (
        status: response.statusCode,
        body: Map<String, dynamic>.from(decoded),
      );
    } finally {
      client.close(force: true);
    }
  }

  test('GET /local/orders responde do SQLite do principal', () async {
    final response = await call('GET', '/local/orders');

    expect(response.status, HttpStatus.ok);
    final result = response.body['result'] as Map<String, dynamic>;
    expect(result['count'], 1);
    expect((result['results'] as List).single['sequence'], 10);
  });

  test('GET /local/printers entrega a configuração dos periféricos (§18)', () async {
    // A configuração é centralizada no principal; a execução continua no
    // terminal que alcança o equipamento fisicamente.
    final response = await call('GET', '/local/printers');

    final result = response.body['result'] as Map<String, dynamic>;
    expect((result['results'] as List).single['name'], 'Cozinha');
  });

  test('POST /local/orders grava no SQLite e enfileira a sincronização', () async {
    final response = await call(
      'POST',
      '/local/orders',
      body: {
        'restaurant': restaurantId,
        'order_type': 'counter',
        'operation_id': 'operacao-do-garcom-0001',
      },
    );

    expect(response.status, HttpStatus.ok);
    final result = response.body['result'] as Map<String, dynamic>;
    final orderId = '${result['id']}';
    expect(orderId, startsWith('offline-'));

    // O pedido existe no banco do principal — é dele que os outros terminais
    // vão ler daqui em diante.
    final stored = await gateway.orders.read(orderId);
    expect(stored, isNotNull);
    final queued = await gateway.queue.entries(scope: gateway.scope!);
    expect(queued.single.path, '/orders/');
  });

  test('a mesma operação enviada duas vezes não cria dois pedidos (§7)', () async {
    final primeira = await call(
      'POST',
      '/local/orders',
      body: {
        'restaurant': restaurantId,
        'order_type': 'counter',
        'operation_id': 'operacao-do-garcom-0002',
      },
    );
    final segunda = await call(
      'POST',
      '/local/orders',
      nonce: 'nonce-do-aparelho-2',
      body: {
        'restaurant': restaurantId,
        'order_type': 'counter',
        'operation_id': 'operacao-do-garcom-0002',
      },
    );

    expect(
      (segunda.body['result'] as Map)['id'],
      (primeira.body['result'] as Map)['id'],
    );
    final page = await gateway.orders.list();
    expect(page.count, 2); // o pedido pré-existente + UM novo
  });

  test('a rota /local é o mesmo recurso de /v1/read', () {
    expect(
      LocalTopologyService.normalizeLocalPath('/local/orders'),
      '/orders/',
    );
    expect(
      LocalTopologyService.normalizeLocalPath('/local/menu/products/'),
      '/menu/products/',
    );
    // Uma rota de recurso já normalizada passa intacta.
    expect(LocalTopologyService.normalizeLocalPath('/orders/'), '/orders/');
  });

  test('rota local desconhecida é recusada', () async {
    final response = await call('GET', '/local/segredos');

    expect(response.status, greaterThanOrEqualTo(HttpStatus.badRequest));
  });
}

Future<int> _freePort() async {
  final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
  final port = socket.port;
  await socket.close();
  return port;
}

Future<void> _deleteTemporaryDirectory(Directory directory) async {
  for (var attempt = 0; attempt < 5; attempt++) {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
      return;
    } on FileSystemException {
      await Future<void>.delayed(const Duration(milliseconds: 120));
    }
  }
}

class _MemorySecretStorage implements TopologySecretStorage {
  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async => this.value = value;
}
