import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/features/home/data/pdv_repository.dart';
import 'package:starchef_pdv/features/home/presentation/pdv_presenter.dart';

void main() {
  test('abre no restaurante do caixa vinculado ao usuário', () async {
    final api = _apiWithCatalog(
      cashStations: const [
        {
          'id': 'cash-2',
          'restaurant': 'restaurant-2',
          'operators': ['user-1'],
          'is_active': true,
        },
      ],
    );
    addTearDown(api.dispose);
    final presenter = PdvPresenter(
      PdvRepository(api: api, accessToken: 'token'),
    );

    final result = await presenter.load(
      userId: 'user-1',
      userRestaurantId: 'restaurant-1',
    );

    expect(result.selectedRestaurantId, 'restaurant-2');
  });

  test('sem caixa vinculado mantém o restaurante do perfil', () async {
    final api = _apiWithCatalog(cashStations: const []);
    addTearDown(api.dispose);
    final presenter = PdvPresenter(
      PdvRepository(api: api, accessToken: 'token'),
    );

    final result = await presenter.load(
      userId: 'user-1',
      userRestaurantId: 'restaurant-1',
    );

    expect(result.selectedRestaurantId, 'restaurant-1');
  });

  test('uma unidade escolhida na sessão continua selecionada', () async {
    var initialCashLookupCount = 0;
    final api = _apiWithCatalog(
      cashStations: const [
        {
          'id': 'cash-2',
          'restaurant': 'restaurant-2',
          'operators': ['user-1'],
          'is_active': true,
        },
      ],
      onInitialCashLookup: () => initialCashLookupCount++,
    );
    addTearDown(api.dispose);
    final presenter = PdvPresenter(
      PdvRepository(api: api, accessToken: 'token'),
    );

    final result = await presenter.load(
      selectedRestaurantId: 'restaurant-1',
      userId: 'user-1',
      userRestaurantId: 'restaurant-2',
    );

    expect(result.selectedRestaurantId, 'restaurant-1');
    expect(initialCashLookupCount, 0);
  });
}

ApiClient _apiWithCatalog({
  required List<Map<String, dynamic>> cashStations,
  void Function()? onInitialCashLookup,
}) => ApiClient(
  baseUrl: 'http://starchef.test/api/v1',
  client: MockClient((request) async {
    final path = request.url.path;
    if (path.endsWith('/restaurants/')) {
      return _page(const [
        {'id': 'restaurant-1', 'trade_name': 'Unidade 1'},
        {'id': 'restaurant-2', 'trade_name': 'Unidade 2'},
      ]);
    }
    if (path.endsWith('/cash-stations/')) {
      if (!request.url.queryParameters.containsKey('restaurant')) {
        onInitialCashLookup?.call();
      }
      return _page(cashStations);
    }
    if (path.endsWith('/menu/products/') ||
        path.endsWith('/menu/categories/') ||
        path.endsWith('/tables/') ||
        path.endsWith('/commands/')) {
      return _page(const []);
    }
    return http.Response('{}', 404);
  }),
);

http.Response _page(List<Map<String, dynamic>> results) => http.Response(
  jsonEncode({'results': results}),
  200,
  headers: const {'content-type': 'application/json'},
);
