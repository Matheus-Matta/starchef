import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/realtime_client.dart';
import 'package:starchef_pdv_desktop/core/network/response_cache.dart';

/// O cache de leitura abre a tela na hora — e nunca mostra o que não é desta
/// sessão, nem o que uma escrita ou evento já tornou velho.
void main() {
  const escopo = 'http://loja|conta-1:user-1';
  Map<String, dynamic> lista(String nome) => {
    'results': [
      {'name': nome},
    ],
    'next': null,
  };

  group('ResponseCache', () {
    test('mesma consulta acerta; outro restaurante, conta ou usuário erra', () {
      final cache = ResponseCache()
        ..store(escopo, '/commands/', {'restaurant': 'r1'}, lista('c1'));

      expect(cache.peek(escopo, '/commands/', {'restaurant': 'r1'}), isNotNull);
      expect(cache.peek(escopo, '/commands/', {'restaurant': 'r2'}), isNull);
      expect(
        cache.peek('http://loja|conta-2:user-1', '/commands/', {
          'restaurant': 'r1',
        }),
        isNull,
      );
      expect(
        cache.peek('http://loja|conta-1:user-9', '/commands/', {
          'restaurant': 'r1',
        }),
        isNull,
      );
    });

    test('ordem dos parâmetros não muda a chave', () {
      final cache = ResponseCache()
        ..store(escopo, '/menu/products/', {'a': 1, 'b': 2}, lista('p'));

      expect(
        cache.peek(escopo, '/menu/products/', {'b': 2, 'a': 1}),
        isNotNull,
      );
    });

    test('pedido, caixa e autenticação nunca entram', () {
      final cache = ResponseCache()
        ..store(escopo, '/orders/', null, lista('o'))
        ..store(escopo, '/cash-register/current/', null, lista('x'))
        ..store(escopo, '/auth/me/', null, lista('u'));

      expect(cache.length, 0);
    });

    test('escrita em pedido apaga comandas e mesas, mas não o cardápio', () {
      final cache = ResponseCache()
        ..store(escopo, '/commands/', null, lista('c'))
        ..store(escopo, '/tables/', null, lista('t'))
        ..store(escopo, '/menu/products/', null, lista('p'));

      cache.invalidateForWrite('/orders/abc/pay/');

      expect(cache.peek(escopo, '/commands/', null), isNull);
      expect(cache.peek(escopo, '/tables/', null), isNull);
      expect(cache.peek(escopo, '/menu/products/', null), isNotNull);
    });

    test(
      'evento do cardápio apaga só o cardápio; recurso desconhecido apaga tudo',
      () {
        final cache = ResponseCache()
          ..store(escopo, '/commands/', null, lista('c'))
          ..store(escopo, '/menu/products/', null, lista('p'));

        cache.invalidateForResource('menu.product');
        expect(cache.peek(escopo, '/menu/products/', null), isNull);
        expect(cache.peek(escopo, '/commands/', null), isNotNull);

        cache.invalidateForResource('algo.novo');
        expect(cache.length, 0);
      },
    );

    test('limite de entradas tira a mais antiga', () {
      final cache = ResponseCache(maxEntries: 2)
        ..store(escopo, '/commands/', {'p': 1}, lista('1'))
        ..store(escopo, '/commands/', {'p': 2}, lista('2'))
        ..store(escopo, '/commands/', {'p': 3}, lista('3'));

      expect(cache.length, 2);
      expect(cache.peek(escopo, '/commands/', {'p': 1}), isNull);
      expect(cache.peek(escopo, '/commands/', {'p': 3}), isNotNull);
    });

    test('entrada vencida não é servida', () {
      var agora = DateTime(2026, 10, 2, 12);
      final cache = ResponseCache(
        maxAge: const Duration(minutes: 30),
        clock: () => agora,
      )..store(escopo, '/commands/', null, lista('c'));

      agora = agora.add(const Duration(minutes: 31));

      expect(cache.peek(escopo, '/commands/', null), isNull);
    });
  });

  group('ApiClient com cache', () {
    late List<String> pedidos;
    const token = 'x.eyJhY2NvdW50X2lkIjoiYzEiLCJ1c2VyX2lkIjoidTEifQ.y';

    ApiClient cliente({int status = 200}) {
      pedidos = [];
      return ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((request) async {
          pedidos.add('${request.method} ${request.url.path}');
          return http.Response(
            '{"results": [{"id": 1}], "next": null}',
            status,
          );
        }),
      );
    }

    test(
      'GET de catálogo fica guardado; escrita de pedido apaga a comanda',
      () async {
        final api = cliente();
        await api.get(
          '/commands/',
          query: {'restaurant': 'r1'},
          accessToken: token,
        );
        expect(
          api.peek(
            '/commands/',
            query: {'restaurant': 'r1'},
            accessToken: token,
          ),
          isNotNull,
        );

        await api.post(
          '/orders/o1/attach-commands/',
          body: const {},
          accessToken: token,
        );

        expect(
          api.peek(
            '/commands/',
            query: {'restaurant': 'r1'},
            accessToken: token,
          ),
          isNull,
        );
      },
    );

    test('resposta de erro não é guardada', () async {
      final api = cliente(status: 503);
      await expectLater(
        api.get('/commands/', accessToken: token),
        throwsA(anything),
      );

      expect(api.peek('/commands/', accessToken: token), isNull);
    });

    test(
      'logout, troca de servidor e reconexão do tempo real limpam tudo',
      () async {
        final api = cliente();
        Future<void> encher() => api.get('/menu/products/', accessToken: token);

        await encher();
        await api.clearSession();
        expect(api.cache.length, 0);

        await encher();
        await api.updateBaseUrl('http://outra.test/api/v1');
        expect(api.cache.length, 0);

        await encher();
        api.notifyRealtimeConnected();
        expect(api.cache.length, 0);
      },
    );

    test('evento de comanda apaga a lista de comandas', () async {
      final api = cliente();
      await api.get('/commands/', accessToken: token);

      api.applyRealtimeEvent(
        const RealtimeEvent('model.updated', {
          'resource': 'restaurants.command',
        }),
        restaurantId: 'r1',
      );

      expect(api.peek('/commands/', accessToken: token), isNull);
    });
  });
}
