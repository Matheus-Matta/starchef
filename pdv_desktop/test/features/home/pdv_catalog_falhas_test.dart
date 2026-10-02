import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/core/network/response_cache.dart';
import 'package:starchef_pdv_desktop/features/home/data/pdv_repository.dart';

/// O catálogo com a rede e o servidor falhando: a tela nunca fica com meio
/// catálogo, nunca quebra por trás, e o erro chega como `ApiException`.
void main() {
  const token = 'x.eyJhY2NvdW50X2lkIjoiYzEiLCJ1c2VyX2lkIjoidTEifQ.y';
  late DateTime agora;
  late http.Response Function(http.Request) servidor;

  PdvRepository repositorio() {
    agora = DateTime(2026, 10, 2, 12);
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      cache: ResponseCache(clock: () => agora),
      requestTimeout: const Duration(seconds: 2),
      client: MockClient((request) async => servidor(request)),
    );
    return PdvRepository(api: api, accessToken: token);
  }

  http.Response lista(String nome, {String? next}) => http.Response(
    '{"results": [{"id": 1, "name": "$nome"}], "next": ${next == null ? 'null' : '"$next"'}}',
    200,
  );

  test('servidor cai na releitura por trás: a cópia fica e nada estoura', () async {
    servidor = (_) => lista('X-Burger');
    final repo = repositorio();
    final sinais = <String>[];
    final ouvindo = repo.api.signals.changes.listen(sinais.add);
    await repo.loadCatalog('r1');

    servidor = (_) => http.Response('{"detail": "fora"}', 503);
    agora = agora.add(const Duration(seconds: 30));
    final mostrado = await repo.loadCatalog('r1');
    await Future<void>.delayed(const Duration(milliseconds: 300));

    expect(mostrado.products.single['name'], 'X-Burger');
    expect(sinais, isNot(contains('realtime:pdv')));
    expect(repo.cachedCatalog('r1'), isNotNull);
    await ouvindo.cancel();
  });

  test('500 na primeira carga chega como ApiException e não guarda nada', () async {
    servidor = (_) => http.Response('{"error": {"message": "erro interno"}}', 500);
    final repo = repositorio();

    await expectLater(repo.loadCatalog('r1'), throwsA(isA<ApiException>()));
    expect(repo.cachedCatalog('r1'), isNull);
  });

  test('uma página de comandas falha: nunca fica meio catálogo no cache', () async {
    servidor = (request) {
      final path = request.url.path;
      if (path.endsWith('/commands/')) {
        return request.url.queryParameters['page'] == '1'
            ? lista('C1', next: 'http://starchef.test/api/v1/commands/?page=2')
            : http.Response('{"detail": "fora"}', 503);
      }
      return lista('ok');
    };
    final repo = repositorio();

    await expectLater(repo.loadCatalog('r1'), throwsA(isA<ApiException>()));
    expect(repo.cachedCatalog('r1'), isNull);
  });

  test('servidor devolve lixo no lugar de JSON: ApiException, não TypeError', () async {
    servidor = (_) => http.Response('<html>proxy caiu</html>', 200);
    final repo = repositorio();

    await expectLater(repo.loadCatalog('r1'), throwsA(isA<ApiException>()));
    expect(repo.cachedCatalog('r1'), isNull);
  });

  test('resposta sem "results" vira lista vazia, não exceção', () async {
    servidor = (_) => http.Response('{"next": null}', 200);
    final repo = repositorio();

    final catalogo = await repo.loadCatalog('r1');

    expect(catalogo.products, isEmpty);
    expect(catalogo.commands, isEmpty);
  });
}
