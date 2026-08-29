import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';

const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEifQ.'
    'assinatura-irrelevante-no-teste';

/// Caixa Principal simulado.
class FakePrincipal implements MutationRelay {
  FakePrincipal({this.available = true, this.data = const {}});

  bool available;
  Map<String, dynamic> data;
  final List<String> readPaths = [];
  final List<String> relayedPaths = [];

  @override
  Future<bool> probe() async => available;

  @override
  Future<Map<String, dynamic>> read(RelayRead request) async {
    if (!available) {
      throw const MutationRelayUnavailable('Principal fora do ar.');
    }
    readPaths.add(request.path);
    return {...data, 'path': request.path};
  }

  @override
  Future<Map<String, dynamic>> relay(RelayMutation mutation) async {
    if (!available) {
      throw const MutationRelayUnavailable('Principal fora do ar.');
    }
    relayedPaths.add(mutation.path);
    return {'id': 'do-principal'};
  }
}

void main() {
  late Directory directory;
  var counter = 0;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-principal');
  });

  tearDown(() async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  ApiClient clientWith(http.Client transport) {
    counter += 1;
    return ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: transport,
      offlineStore: OfflineStore(
        file: File(
          '${directory.path}${Platform.pathSeparator}p-$counter.sqlite',
        ),
      ),
    );
  }

  test('o secundário lê pelo principal, não pela nuvem', () async {
    var cloudCalls = 0;
    final api = clientWith(
      MockClient((_) async {
        cloudCalls += 1;
        return http.Response(
          jsonEncode({'results': <dynamic>[], 'origem': 'nuvem'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(api.dispose);
    final principal = FakePrincipal(data: {'origem': 'principal'});
    api.attachMutationRelay(principal);

    final result = await api.get('/orders/', accessToken: _token);

    // É o principal que tem a verdade da loja; ir à nuvem por trás dele
    // recriaria a divergência entre caixas.
    expect(result['origem'], 'principal');
    expect(result['_from_principal'], isTrue);
    expect(principal.readPaths, ['/orders/']);
    expect(cloudCalls, 0);
  });

  test('com a nuvem fora e a rede local de pé, o pedido abre', () async {
    final api = clientWith(
      MockClient((_) async => throw const SocketException('sem internet')),
    );
    addTearDown(api.dispose);
    api.attachMutationRelay(FakePrincipal(data: {'id': 'order-1'}));

    final result = await api.get('/orders/order-1/', accessToken: _token);

    // Este era o buraco: o secundário gravava pelo principal mas não
    // conseguia ler o pedido que ia alterar.
    expect(result['id'], 'order-1');
  });

  test('principal fora cai para a nuvem', () async {
    final api = clientWith(
      MockClient(
        (_) async => http.Response(
          jsonEncode({'origem': 'nuvem'}),
          200,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    addTearDown(api.dispose);
    api.attachMutationRelay(FakePrincipal(available: false));

    final result = await api.get('/orders/', accessToken: _token);

    expect(result['origem'], 'nuvem');
  });

  test('principal e nuvem fora: sobra a cópia local', () async {
    var cloudUp = true;
    final api = clientWith(
      MockClient((_) async {
        if (!cloudUp) throw const SocketException('sem internet');
        return http.Response(
          jsonEncode({'origem': 'nuvem'}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    addTearDown(api.dispose);
    final principal = FakePrincipal(available: false);
    api.attachMutationRelay(principal);

    await api.get('/orders/', accessToken: _token);
    cloudUp = false;

    final cached = await api.get('/orders/', accessToken: _token);

    // O caixa não pode parar de vender porque os dois canais caíram.
    expect(cached['_offline_cache'], isTrue);
    expect(cached['origem'], 'nuvem');
  });

  test('uma recusa do servidor não é repetida pela nuvem', () async {
    var cloudCalls = 0;
    final api = clientWith(
      MockClient((_) async {
        cloudCalls += 1;
        return http.Response('{}', 200);
      }),
    );
    addTearDown(api.dispose);
    api.attachMutationRelay(_RefusingPrincipal());

    await expectLater(
      () => api.get('/orders/', accessToken: _token),
      throwsA(isA<ApiException>()),
    );
    // O principal alcançou o servidor e ele recusou; tentar de novo pela
    // nuvem daria o mesmo 403 e esconderia a causa.
    expect(cloudCalls, 0);
  });

  group('o secundário não grava sem o principal', () {
    test('com o principal fora, a alteração é recusada', () async {
      var cloudCalls = 0;
      final api = clientWith(
        MockClient((_) async {
          cloudCalls += 1;
          return http.Response('{"id":"da-nuvem"}', 201);
        }),
      );
      addTearDown(api.dispose);
      api.attachMutationRelay(FakePrincipal(available: false));

      await expectLater(
        () => api.post(
          '/orders/order-1/items/',
          body: const {'product': 'p1', 'quantity': 1},
          accessToken: _token,
        ),
        throwsA(
          isA<ApiException>().having(
            (error) => error.message,
            'message',
            contains('Caixa Principal está indisponível'),
          ),
        ),
      );

      // Nem pela nuvem, nem na fila local: as duas rotas deixariam o
      // principal sem saber de uma venda que os outros caixas leem dele.
      expect(cloudCalls, 0);
      expect(await api.pendingOperations(), 0);
    });

    test('com a nuvem fora mas o principal de pé, grava normalmente', () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem internet')),
      );
      addTearDown(api.dispose);
      final principal = FakePrincipal();
      api.attachMutationRelay(principal);

      final result = await api.post(
        '/orders/order-1/items/',
        body: const {'product': 'p1', 'quantity': 1},
        accessToken: _token,
      );

      expect(result['id'], 'do-principal');
      expect(principal.relayedPaths, ['/orders/order-1/items/']);
      expect(await api.pendingOperations(), 0);
    });

    test('cadastro de cliente vai ao principal, não à nuvem', () async {
      // Era a última exceção: o cliente ia direto para a nuvem porque "não
      // pertence ao atendimento em curso". Na prática, era um segundo caminho
      // até a nuvem saindo de um terminal que não deveria ter nenhum.
      var cloudCalls = 0;
      final api = clientWith(
        MockClient((_) async {
          cloudCalls += 1;
          return http.Response('{"id":"da-nuvem"}', 201);
        }),
      );
      addTearDown(api.dispose);
      final principal = FakePrincipal();
      api.attachMutationRelay(principal);

      final result = await api.post(
        '/customers/',
        body: const {'name': 'Maria'},
        accessToken: _token,
      );

      expect(cloudCalls, 0);
      expect(result['id'], 'do-principal');
      expect(principal.relayedPaths, ['/customers/']);
    });

    test('sem o principal, o cliente também não vai pela nuvem', () async {
      var cloudCalls = 0;
      final api = clientWith(
        MockClient((_) async {
          cloudCalls += 1;
          return http.Response('{"id":"da-nuvem"}', 201);
        }),
      );
      addTearDown(api.dispose);
      api.attachMutationRelay(FakePrincipal(available: false));

      await expectLater(
        () => api.post(
          '/customers/',
          body: const {'name': 'Maria'},
          accessToken: _token,
        ),
        throwsA(isA<ApiException>()),
      );

      expect(cloudCalls, 0);
      expect(await api.pendingOperations(), 0);
    });

    test('operação que exige servidor também é recusada', () async {
      final api = clientWith(
        MockClient((_) async => http.Response('{}', 200)),
      );
      addTearDown(api.dispose);
      api.attachMutationRelay(FakePrincipal());

      // Impressão não passa pelo relay; num secundário ela é do principal.
      await expectLater(
        () => api.post(
          '/orders/order-1/print/',
          body: const {},
          accessToken: _token,
        ),
        throwsA(isA<ApiException>()),
      );
    });

    test('um caixa principal continua usando a própria fila', () async {
      final api = clientWith(
        MockClient((_) async => throw const SocketException('sem internet')),
      );
      addTearDown(api.dispose);
      // Sem relay anexado = este terminal é o principal.

      final queued = await api.post(
        '/orders/order-1/items/',
        body: const {'product': 'p1', 'quantity': 1},
        accessToken: _token,
      );

      expect(queued['_offline_pending'], isTrue);
      expect(await api.pendingOperations(), 1);
    });
  });

  test('a leitura pelo principal alimenta o cache local', () async {
    final api = clientWith(
      MockClient((_) async => throw const SocketException('sem internet')),
    );
    addTearDown(api.dispose);
    final principal = FakePrincipal(data: {'origem': 'principal'});
    api.attachMutationRelay(principal);

    await api.get('/orders/', accessToken: _token);
    principal.available = false;

    final cached = await api.get('/orders/', accessToken: _token);

    // Se o principal também cair depois, o que ele já entregou continua valendo.
    expect(cached['origem'], 'principal');
    expect(cached['_offline_cache'], isTrue);
  });
}

class _RefusingPrincipal implements MutationRelay {
  @override
  Future<bool> probe() async => true;

  @override
  Future<Map<String, dynamic>> read(RelayRead request) async =>
      throw const ApiException('Sem permissão.', statusCode: 403);

  @override
  Future<Map<String, dynamic>> relay(RelayMutation mutation) async =>
      throw const ApiException('Sem permissão.', statusCode: 403);
}
