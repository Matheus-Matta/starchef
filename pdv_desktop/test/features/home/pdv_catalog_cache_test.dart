import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/response_cache.dart';
import 'package:starchef_pdv_desktop/features/home/data/pdv_repository.dart';

/// O catálogo abre com a última cópia e se corrige sozinho por trás.
void main() {
  const token = 'x.eyJhY2NvdW50X2lkIjoiYzEiLCJ1c2VyX2lkIjoidTEifQ.y';
  late List<String> leituras;
  late String nomeDoProduto;
  late DateTime agora;

  PdvRepository repositorio() {
    leituras = [];
    nomeDoProduto = 'X-Burger';
    agora = DateTime(2026, 10, 2, 12);
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      cache: ResponseCache(clock: () => agora),
      client: MockClient((request) async {
        leituras.add('${request.method} ${request.url.path}');
        final nome = request.url.path.endsWith('/menu/products/')
            ? nomeDoProduto
            : 'x';
        return http.Response(
          '{"results": [{"id": 1, "name": "$nome"}], "next": null}',
          200,
        );
      }),
    );
    return PdvRepository(api: api, accessToken: token);
  }

  Future<void> rodarPorTras() => Future<void>.delayed(Duration.zero);

  test(
    'a primeira carga vai ao servidor; reabrir logo em seguida não',
    () async {
      final repo = repositorio();

      await repo.loadCatalog('r1');
      final depoisDaPrimeira = leituras.length;
      final segunda = await repo.loadCatalog('r1');
      await rodarPorTras();

      expect(depoisDaPrimeira, 6);
      expect(leituras.length, depoisDaPrimeira);
      expect(segunda.products.single['name'], 'X-Burger');
    },
  );

  test(
    'cópia antiga aparece na hora e a tela é avisada se o servidor mudou',
    () async {
      final repo = repositorio();
      final sinais = <String>[];
      final ouvindo = repo.api.signals.changes.listen(sinais.add);
      await repo.loadCatalog('r1');
      nomeDoProduto = 'X-Salada';
      agora = agora.add(const Duration(seconds: 30));

      final mostrado = await repo.loadCatalog('r1');
      expect(mostrado.products.single['name'], 'X-Burger');

      await Future<void>.delayed(const Duration(milliseconds: 300));
      expect(sinais, contains('realtime:pdv'));
      expect(
        (await repo.loadCatalog('r1')).products.single['name'],
        'X-Salada',
      );
      await ouvindo.cancel();
    },
  );

  test('sem mudança no servidor, a tela não é incomodada', () async {
    final repo = repositorio();
    final sinais = <String>[];
    final ouvindo = repo.api.signals.changes.listen(sinais.add);
    await repo.loadCatalog('r1');
    agora = agora.add(const Duration(seconds: 30));

    await repo.loadCatalog('r1');
    await Future<void>.delayed(const Duration(milliseconds: 300));

    expect(sinais, isNot(contains('realtime:pdv')));
    await ouvindo.cancel();
  });

  test('depois de uma escrita, a próxima carga vai ao servidor', () async {
    final repo = repositorio();
    await repo.loadCatalog('r1');
    await repo.post('/orders/o1/attach-commands/', const {'commands': []});
    final antes = leituras.length;

    await repo.loadCatalog('r1');

    expect(leituras.length, greaterThan(antes));
  });

  test(
    'depois de uma venda, só comandas e mesas vão ao servidor de novo',
    () async {
      // A venda mexe em comanda e mesa, e só elas saem do cache. Antes, faltar
      // UMA lista fazia o PDV baixar as seis — o cardápio inteiro a cada venda.
      final repo = repositorio();
      await repo.loadCatalog('r1');
      await repo.post('/orders/o1/pay/', const {'amount': 10});
      leituras.clear();

      final catalogo = await repo.loadCatalog('r1');

      expect(leituras.toSet(), {
        'GET /api/v1/tables/',
        'GET /api/v1/commands/',
      });
      expect(catalogo.products.single['name'], 'X-Burger');
    },
  );

  test('a lista de impressoras da venda seguinte vem do cache', () async {
    final repo = repositorio();
    final query = {'restaurant': 'r1', 'is_active': true, 'page_size': 100};
    await repo.listCached('/printers/', query: query);
    leituras.clear();

    final impressoras = await repo.listCached('/printers/', query: query);

    expect(leituras, isEmpty);
    expect(impressoras, hasLength(1));
  });

  test('outro restaurante não aproveita o catálogo deste', () async {
    final repo = repositorio();
    await repo.loadCatalog('r1');

    expect(repo.cachedCatalog('r2'), isNull);
  });
}
