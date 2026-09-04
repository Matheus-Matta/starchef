import '../../../core/network/api_client.dart';

typedef JsonMap = Map<String, dynamic>;

/// Camada de dados do PDV.
///
/// Centraliza autenticação e o formato paginado da API. A apresentação não
/// precisa conhecer `results`, token Bearer ou detalhes do transporte offline.
class PdvRepository {
  const PdvRepository({required this.api, required this.accessToken});

  final ApiClient api;
  final String accessToken;

  Future<List<JsonMap>> list(String path, {Map<String, dynamic>? query}) async {
    final response = await api.get(
      path,
      query: query,
      accessToken: accessToken,
    );
    return ((response['results'] ?? const []) as List).cast<JsonMap>();
  }

  Future<JsonMap> get(String path) => api.get(path, accessToken: accessToken);

  Future<JsonMap> post(String path, JsonMap body) =>
      api.post(path, body: body, accessToken: accessToken);

  Future<JsonMap> patch(String path, JsonMap body) =>
      api.patch(path, body: body, accessToken: accessToken);

  Future<JsonMap> delete(String path, [JsonMap? body]) =>
      api.delete(path, body: body, accessToken: accessToken);

  Future<PdvCatalog> loadCatalog(String restaurantId) async {
    final query = {'page_size': 300, 'restaurant': restaurantId};
    final responses = await Future.wait([
      list('/cash-stations/', query: {...query, 'is_active': true}),
      list('/menu/products/', query: {...query, 'is_active': true}),
      list('/menu/categories/', query: {'page_size': 100, 'is_active': true}),
      list('/tables/', query: query),
      // Mesas entram no cache para o vínculo opcional da comanda; comandas são
      // o contexto de abertura do pedido. Ambos precisam funcionar sem rede.
      list('/commands/', query: {...query, 'is_active': true}),
      // Usa exatamente a mesma consulta da tela de recebimento. O ApiClient
      // persiste essa resposta no SQLite, portanto as formas continuam
      // disponíveis quando o terminal perder a conexão depois da carga.
      list(
        '/payments/methods/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      ),
    ]);
    return PdvCatalog(
      cashStations: responses[0],
      products: responses[1],
      categories: responses[2],
      tables: responses[3],
      commands: responses[4],
      paymentMethods: responses[5],
    );
  }
}

class PdvCatalog {
  const PdvCatalog({
    required this.cashStations,
    required this.products,
    required this.categories,
    required this.tables,
    required this.commands,
    required this.paymentMethods,
  });

  final List<JsonMap> cashStations;
  final List<JsonMap> products;
  final List<JsonMap> categories;
  final List<JsonMap> tables;
  final List<JsonMap> commands;
  final List<JsonMap> paymentMethods;
}
