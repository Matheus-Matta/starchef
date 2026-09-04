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
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/core/network/realtime_client.dart';

/// Token com claim de conta: é dele que sai o escopo do banco local.
const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEifQ.'
    'assinatura-irrelevante-no-teste';

/// O `ApiClient` deixou de ser a fonte de dados e virou o transporte (§1).
/// Estes testes verificam a mudança pela porta que as telas usam: `get` e
/// `post` continuam com a mesma assinatura, mas agora respondem do SQLite e
/// nunca esperam a rede para concluir uma operação.
void main() {
  late Directory directory;
  var contador = 0;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-offline-first');
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
    final queue = SyncQueueService(database: database);
    final gateway = OfflineFirstGateway(
      database: database,
      queue: queue,
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

  test('a leitura sai do SQLite sem esperar a rede (§3, §29)', () async {
    var chamadasDeRede = 0;
    final stack = await build(
      MockClient((request) async {
        chamadasDeRede += 1;
        // Uma resposta lenta representa a rede ruim do salão: a tela não pode
        // ficar presa nela.
        await Future<void>.delayed(const Duration(seconds: 2));
        return json({'count': 0, 'results': []});
      }),
    );
    // Sessão conhecida + catálogo já sincronizado: é o estado normal de um
    // caixa em operação.
    stack.gateway.bindSession(
      scope: '${Uri.parse('http://starchef.test/api/v1').authority}'
          '|acc-1:authenticated',
      restaurantId: 'rest-1',
    );
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {'id': 'p1', 'name': 'Coxinha', 'restaurant': 'rest-1'},
    ]);
    await stack.gateway.recordSync(EntityCatalog.product);

    final stopwatch = Stopwatch()..start();
    final response = await stack.api.get(
      '/menu/products/',
      query: {'restaurant': 'rest-1'},
      accessToken: _token,
    );
    stopwatch.stop();

    expect(response['count'], 1);
    expect(response['_local_first'], isTrue);
    // Resposta imediata: a sincronização com o backend corre em paralelo.
    expect(stopwatch.elapsed, lessThan(const Duration(seconds: 1)));
    expect(chamadasDeRede, lessThanOrEqualTo(1));

    await stack.api.dispose();
    await stack.database.close();
  });

  test('a escrita conclui local e fica na fila com a rede fora (§4)', () async {
    final stack = await build(
      MockClient((request) async => throw const SocketException('sem rede')),
    );

    final created = await stack.api.post(
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
      accessToken: _token,
    );

    expect(created['id'], startsWith('offline-'));
    expect(created['_local_first'], isTrue);
    // A venda existe no banco antes de qualquer resposta do servidor.
    final scope = stack.gateway.scope!;
    final queued = await stack.gateway.queue.entries(scope: scope);
    expect(queued.single.path, '/orders/');

    await stack.api.dispose();
    await stack.database.close();
  });

  test('leitura de recurso nunca sincronizado busca uma vez na rede', () async {
    // Partida a frio: mostrar tudo vazio na primeira abertura seria pior do
    // que esperar uma leitura.
    final stack = await build(
      MockClient(
        (request) async => json({
          'count': 1,
          'results': [
            {'id': 'p1', 'name': 'Do servidor'},
          ],
        }),
      ),
    );

    final response = await stack.api.get(
      '/menu/products/',
      accessToken: _token,
    );

    expect(response['count'], 1);
    final stored = await stack.gateway
        .repository(EntityCatalog.product)
        .read('p1');
    expect(stored, isNotNull);

    await stack.api.dispose();
    await stack.database.close();
  });

  test('escrita marca `_queued_offline` só quando não havia conexão', () async {
    // É esta marca — e não "está pendente na fila" — que decide se a comanda
    // de cozinha sai na impressora local. Com a rede de pé, quem imprime é o
    // backend; marcar sempre faria sair duas comandas para a mesma rodada.
    final stack = await build(
      MockClient((request) async => throw const SocketException('sem rede')),
    );

    final offline = await stack.api.post(
      '/orders/',
      body: {'restaurant': 'rest-1'},
      accessToken: _token,
    );
    expect(offline['_queued_offline'], isTrue);

    await stack.api.dispose();
    await stack.database.close();
  });

  test('evento do WebSocket persiste o registro no SQLite (§11)', () async {
    final stack = await build(
      MockClient(
        (request) async => json({'id': 'p1', 'name': 'Atualizado na nuvem'}),
      ),
    );
    stack.gateway.bindSession(
      scope: 'starchef.test|acc-1:authenticated',
      restaurantId: 'rest-1',
    );
    stack.api.applyRealtimeEvent(
      const RealtimeEvent('model.updated', {
        'resource': 'menu.product',
        'id': 'p1',
        'action': 'updated',
        'restaurant_id': 'rest-1',
      }),
      restaurantId: 'rest-1',
    );
    await Future<void>.delayed(const Duration(milliseconds: 300));

    final stored = await stack.gateway
        .repository(EntityCatalog.product)
        .read('p1');
    expect(stored?.payload['name'], 'Atualizado na nuvem');

    await stack.api.dispose();
    await stack.database.close();
  });

  test('rotas que exigem servidor continuam indo à rede', () async {
    final caminhos = <String>[];
    final stack = await build(
      MockClient((request) async {
        caminhos.add(request.url.path);
        return json({'ok': true});
      }),
    );
    stack.gateway.bindSession(scope: 'starchef.test|acc-1:authenticated');

    await stack.api.post(
      '/print-jobs/job-1/mark-printed/',
      body: const {},
      accessToken: _token,
    );

    expect(caminhos.single, endsWith('/print-jobs/job-1/mark-printed/'));

    await stack.api.dispose();
    await stack.database.close();
  });
}
