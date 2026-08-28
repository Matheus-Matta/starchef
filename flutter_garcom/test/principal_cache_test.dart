import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/relay/principal_client.dart';
import 'package:starchef_garcom/core/relay/relay_gateway.dart';
import 'package:starchef_garcom/core/storage/offline_queue_store.dart';
import 'package:starchef_garcom/core/storage/principal_cache.dart';
import 'package:starchef_garcom/features/auth/domain/waiter_session.dart';
import 'package:starchef_garcom/features/orders/data/orders_repository.dart';

/// **O aparelho continua trabalhando quando o Caixa Principal cai.**
///
/// Ele não fala com a nuvem (§9), então sem cópia local o principal fora do ar
/// significava tela vazia — nem a comanda aberta há um minuto o garçom
/// conseguia abrir. O cache guarda as últimas leituras confirmadas e as serve
/// **marcadas**: é um retrato assumido, não um palpite.
void main() {
  late Directory directory;
  late PrincipalCache cache;

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
    directory = await Directory.systemTemp.createTemp('starchef-garcom-cache');
    cache = PrincipalCache(
      testFile: File(
        '${directory.path}${Platform.pathSeparator}cache.json',
      ),
    );
  });

  tearDown(() async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  OrdersRepository repositoryWith(PrincipalClient client) => OrdersRepository(
    principalClient: client,
    gateway: RelayGateway(
      client: client,
      store: OfflineQueueStore(
        testFile: File(
          '${directory.path}${Platform.pathSeparator}outbox.json',
        ),
      ),
    ),
    session: session,
    principal: const PrincipalConfig(
      host: '127.0.0.1',
      port: 65000,
      secret: 'chave',
      nodeId: 'aparelho',
    ),
    cache: cache,
  );

  test('a mesma rota com filtros diferentes é guardada separada', () {
    final a = PrincipalCache.keyFor('/orders/', {'status': 'open'});
    final b = PrincipalCache.keyFor('/orders/', {'status': 'paid'});
    // A ordem dos filtros não pode gerar duas entradas para a mesma consulta.
    final c = PrincipalCache.keyFor('/orders/', {
      'page_size': 50,
      'status': 'open',
    });
    final d = PrincipalCache.keyFor('/orders/', {
      'status': 'open',
      'page_size': 50,
    });

    expect(a, isNot(b));
    expect(c, d);
  });

  test('guarda e devolve a última resposta confirmada', () async {
    await cache.write('/orders/', {
      'results': [
        {'id': 'pedido-1'},
      ],
    });

    final stored = await cache.read('/orders/');

    expect((stored!.payload['results'] as List).single['id'], 'pedido-1');
    expect(stored.age, lessThan(const Duration(seconds: 5)));
  });

  test('sobrevive a fechar e abrir o app', () async {
    await cache.write('/tables/', {'results': const []});
    await cache.flush();

    final outra = PrincipalCache(
      testFile: File('${directory.path}${Platform.pathSeparator}cache.json'),
    );

    expect(await outra.read('/tables/'), isNotNull);
  });

  test('arquivo corrompido não impede o app de abrir', () async {
    final file = File(
      '${directory.path}${Platform.pathSeparator}cache.json',
    );
    await file.writeAsString('isto não é json');
    final quebrado = PrincipalCache(testFile: file);

    expect(await quebrado.read('/orders/'), isNull);
    // E volta a funcionar a partir da próxima gravação.
    await quebrado.write('/orders/', {'results': const []});
    await quebrado.flush();
    expect(await quebrado.read('/orders/'), isNotNull);
  });

  test('com o principal fora, a leitura sai do cache marcada', () async {
    final client = _FakePrincipalClient();
    final repository = repositoryWith(client);
    client.answer = {
      'results': [
        {'id': 'pedido-1', 'status': 'open'},
      ],
    };
    await repository.openOrders();
    expect(repository.lastReadOrigin.fromCache, isFalse);

    client.reachable = false;
    final orders = await repository.openOrders();

    expect(orders.single['id'], 'pedido-1');
    expect(repository.lastReadOrigin.fromCache, isTrue);
    expect(repository.lastReadOrigin.at, isNotNull);
  });

  test('sem cache e sem principal, a falha continua visível', () async {
    // Fingir que está tudo bem é pior do que dizer que o caixa não respondeu:
    // o garçom precisa saber que não está vendo o salão inteiro.
    final client = _FakePrincipalClient()..reachable = false;

    await expectLater(
      repositoryWith(client).openOrders(),
      throwsA(isA<PrincipalUnavailable>()),
    );
  });

  test('caixa aberto nunca vem de uma cópia velha', () async {
    // Uma sessão "aberta" segundo o cache pode já ter sido fechada; aceitar
    // isso autorizaria um recebimento em dinheiro numa sessão que não existe.
    final client = _FakePrincipalClient();
    final repository = repositoryWith(client);
    client.answer = {'id': 'sessao-1', 'status': 'open'};
    expect(await repository.currentCashRegister(), isNotNull);

    client.reachable = false;

    expect(await repository.currentCashRegister(), isNull);
  });

  test('esquecer o pareamento apaga a cópia local', () async {
    await cache.write('/orders/', {'results': const []});

    await cache.clear();

    expect(await cache.read('/orders/'), isNull);
  });

  test('o cache não cresce sem limite', () async {
    for (var i = 0; i < 130; i++) {
      await cache.write('/rota-$i/', {'results': const []});
    }

    await cache.flush();
    final file = File('${directory.path}${Platform.pathSeparator}cache.json');
    final decoded = jsonDecode(await file.readAsString()) as Map;
    expect(decoded.length, lessThanOrEqualTo(120));
    // As entradas mais recentes são as que ficam.
    expect(decoded.containsKey('/rota-129/'), isTrue);
  });
}

/// Caixa Principal de mentira, no lugar do socket.
class _FakePrincipalClient implements PrincipalClient {
  bool reachable = true;
  Map<String, dynamic> answer = const {'results': []};

  @override
  Future<Map<String, dynamic>> read(
    PrincipalConfig config,
    RelayIdentity identity, {
    required String path,
    Map<String, dynamic>? query,
  }) async {
    if (!reachable) {
      throw const PrincipalUnavailable('O caixa não respondeu.');
    }
    return answer;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      super.noSuchMethod(invocation);
}
