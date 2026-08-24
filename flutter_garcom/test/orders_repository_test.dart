import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/network/api_client.dart';
import 'package:starchef_garcom/core/relay/principal_client.dart';
import 'package:starchef_garcom/core/relay/relay_gateway.dart';
import 'package:starchef_garcom/core/relay/relay_signature.dart';
import 'package:starchef_garcom/core/storage/offline_queue_store.dart';
import 'package:starchef_garcom/features/auth/domain/waiter_session.dart';
import 'package:starchef_garcom/features/orders/data/orders_repository.dart';

/// Contrato com a API, visto pelo relay.
///
/// Existe por causa de um bug real: o app abria pedido em `/orders/open-table/`,
/// endpoint que o backend não tem mais — mesa deixou de ser forma de abrir
/// pedido e virou vínculo da comanda. O sintoma foi "não puxa os dados do
/// pedido", e nenhum teste pegou porque nenhum olhava o caminho chamado.
void main() {
  late _RelaySpy principal;
  late OrdersRepository repository;

  const secret = 'chave-de-pareamento';
  final session = WaiterSession(
    accessToken: 'token',
    refreshToken: 'refresh',
    user: const WaiterUser(
      id: 'garcom-1',
      username: 'maria',
      name: 'Maria',
      accountId: 'conta-1',
      restaurantId: 'restaurante-1',
    ),
  );

  setUp(() async {
    principal = _RelaySpy(secret: secret);
    await principal.start();
    final principalConfig = PrincipalConfig(
      host: '127.0.0.1',
      port: principal.port,
      secret: secret,
      nodeId: 'aparelho-de-teste',
    );
    final gateway = RelayGateway(
      client: PrincipalClient(),
      store: OfflineQueueStore(testFile: _tempFile()),
    )..updateContext(config: principalConfig, identity: session.identity);
    repository = OrdersRepository(
      api: ApiClient(baseUrl: 'http://backend.local/api/v1'),
      principalClient: PrincipalClient(),
      gateway: gateway,
      session: session,
      principal: principalConfig,
    );
  });

  tearDown(() => principal.stop());

  group('abertura de pedido', () {
    test('comanda usa /orders/open-command/', () async {
      await repository.openCommandOrder('comanda-1');

      final envelope = principal.lastRelay;
      expect(envelope['method'], 'POST');
      expect(envelope['path'], '/orders/open-command/');
      expect(envelope['body'], {'command': 'comanda-1'});
    });

    test('balcão, delivery e retirada nascem em /orders/', () async {
      for (final tipo in ['counter', 'delivery', 'takeaway']) {
        await repository.createOrder(tipo);
        expect(principal.lastRelay['path'], '/orders/');
        expect(principal.lastRelay['body'], {'order_type': tipo});
      }
    });
  });

  test('vínculo com a mesa vai na comanda e usa table_id', () async {
    await repository.linkTable(
      commandId: 'comanda-1',
      tableId: 'mesa-9',
      tableLabel: '9',
    );

    final envelope = principal.lastRelay;
    expect(envelope['path'], '/commands/comanda-1/link-table/');
    // O backend espera `table_id`, não `table` — enviar o nome errado devolve
    // 400 com "Informe a mesa para vincular a comanda".
    expect(envelope['body'], {'table_id': 'mesa-9'});
  });

  test('cada gravação leva um operation_id próprio', () async {
    await repository.openCommandOrder('comanda-1');
    final primeiro = principal.lastRelay['operation_id'];
    await repository.openCommandOrder('comanda-1');

    expect(principal.lastRelay['operation_id'], isNot(primeiro));
    expect(
      '${principal.lastRelay['operation_id']}',
      matches(r'^[A-Za-z0-9._:-]{8,160}$'),
      reason: 'formato exigido pelo relay do Caixa Principal',
    );
  });

  group('paginação', () {
    test('produtos pedem uma página por vez, com a busca', () async {
      principal.readPayload = {'results': [], 'next': null};

      await repository.products(page: 3, search: 'coxinha');

      final leitura = principal.lastRead;
      expect(leitura['path'], '/menu/products/');
      expect(leitura['query']['page'], 3);
      expect(leitura['query']['search'], 'coxinha');
      expect(leitura['query']['page_size'], lessThanOrEqualTo(100));
    });

    test('comandas seguem o mesmo caminho paginado', () async {
      principal.readPayload = {'results': [], 'next': null};

      await repository.commands(page: 2);

      expect(principal.lastRead['path'], '/commands/');
      expect(principal.lastRead['query']['page'], 2);
      // Busca vazia não vira parâmetro: sujaria o cache do lado do caixa.
      expect(principal.lastRead['query'].containsKey('search'), isFalse);
    });

    test('`next` da API decide se ainda há páginas', () async {
      principal.readPayload = {
        'results': [
          {'id': 'p1'},
        ],
        'next': 'http://api/menu/products/?page=2',
      };
      final comMais = await repository.products();
      expect(comMais.hasMore, isTrue);
      expect(comMais.rows.single['id'], 'p1');

      principal.readPayload = {'results': [], 'next': null};
      final fim = await repository.products();
      expect(fim.hasMore, isFalse);
    });
  });
}

File _tempFile() {
  final dir = Directory.systemTemp.createTempSync('starchef-garcom-outbox-');
  return File('${dir.path}${Platform.pathSeparator}outbox.json');
}

/// Caixa Principal de mentira que guarda o que recebeu.
class _RelaySpy {
  _RelaySpy({required this.secret});

  final String secret;
  HttpServer? _server;
  int port = 0;

  Map<String, dynamic> lastRelay = const {};
  Map<String, dynamic> lastRead = const {};
  Map<String, dynamic> readPayload = const {'results': []};

  Future<void> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server = server;
    port = server.port;
    server.listen((request) async {
      final body = await utf8.decoder.bind(request).join();
      final decoded = body.isEmpty
          ? <String, dynamic>{}
          : Map<String, dynamic>.from(jsonDecode(body) as Map);

      Map<String, dynamic> resposta;
      if (request.uri.path == '/v1/relay') {
        lastRelay = decoded;
        resposta = {
          'ok': true,
          'result': {'id': 'pedido-1'},
        };
      } else {
        lastRead = {
          'path': decoded['path'],
          'query': Map<String, dynamic>.from(
            decoded['query'] as Map? ?? const {},
          ),
        };
        resposta = {'ok': true, 'result': readPayload};
      }

      final payload = jsonEncode(resposta);
      request.response
        ..statusCode = HttpStatus.ok
        ..headers.contentType = ContentType.json
        ..headers.set(
          'x-starchef-response-signature',
          RelaySignature.response(
            secret: secret,
            requestNonce: request.headers.value('x-starchef-nonce') ?? '',
            statusCode: HttpStatus.ok,
            body: payload,
          ),
        )
        ..write(payload);
      await request.response.close();
    });
  }

  Future<void> stop() async => _server?.close(force: true);
}
