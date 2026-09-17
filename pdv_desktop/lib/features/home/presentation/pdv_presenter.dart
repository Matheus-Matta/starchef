import '../../../core/network/api_exception.dart';
import '../../cash/domain/cash_restaurant_selector.dart';
import '../data/pdv_repository.dart';

/// Presenter da inicialização do PDV.
///
/// Decide o restaurante válido e entrega à View um estado coerente. Regras de
/// seleção e carregamento não ficam espalhadas pelo ciclo de vida do widget.
class PdvPresenter {
  const PdvPresenter(this.repository);

  final PdvRepository repository;

  Future<PdvBootstrap> load({
    String? selectedRestaurantId,
    String? userRestaurantId,
    String? userId,
  }) async {
    final restaurants = await repository.list(
      '/restaurants/',
      query: {'page_size': 300},
    );
    if (restaurants.isEmpty) {
      throw const ApiException(
        'Nenhum restaurante foi vinculado ao seu usuário.',
        statusCode: 403,
      );
    }

    final availableIds = restaurants.map((item) => '${item['id']}').toSet();
    String? linkedRestaurantId;
    // O vínculo do caixa só decide a abertura inicial. Depois que o operador
    // troca a unidade manualmente, `selectedRestaurantId` preserva essa
    // escolha nas recargas da mesma sessão.
    if (selectedRestaurantId == null && userId?.trim().isNotEmpty == true) {
      try {
        final cashStations = await repository.list(
          '/cash-stations/',
          query: {'page_size': 300, 'is_active': true},
        );
        linkedRestaurantId = cashLinkedRestaurantId(
          cashStations: cashStations,
          userId: userId!,
          availableRestaurantIds: availableIds,
        );
      } on ApiException {
        // Sem resposta (ou sem cache) mantém exatamente o fallback anterior.
      }
    }
    final preferred =
        selectedRestaurantId ?? linkedRestaurantId ?? userRestaurantId;
    final restaurantId = preferred != null && availableIds.contains(preferred)
        ? preferred
        : '${restaurants.first['id']}';
    final catalog = await repository.loadCatalog(restaurantId);
    return PdvBootstrap(
      restaurants: restaurants,
      selectedRestaurantId: restaurantId,
      catalog: catalog,
    );
  }
}

class PdvBootstrap {
  const PdvBootstrap({
    required this.restaurants,
    required this.selectedRestaurantId,
    required this.catalog,
  });

  final List<JsonMap> restaurants;
  final String selectedRestaurantId;
  final PdvCatalog catalog;
}
