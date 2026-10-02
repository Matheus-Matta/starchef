import '../../../core/network/api_client.dart';

export 'pdv_catalog.dart';

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

  /// Teto de registros que uma coleção inteira pode trazer para a tela.
  ///
  /// Não é limite de negócio: é a rede de segurança para um cadastro com
  /// dezenas de milhares de linhas não travar a abertura do PDV. Um catálogo
  /// desse tamanho pede busca, não rolagem — e a busca lê do SQLite por índice.
  static const maximumCollectionSize = 5000;

  /// A coleção INTEIRA, seguindo `next` página a página.
  ///
  /// `list()` com `page_size: 300` trazia só a primeira página, e o PDV
  /// mostrava 300 produtos como se fossem todos — o resto do cardápio não
  /// existia no balcão, sem nenhum aviso. A mesma armadilha da comanda que
  /// "não existia" além da página 500: um limite de página assumido como
  /// "grande o bastante". Aqui o tamanho da página segue sendo uma escolha de
  /// desempenho; a quantidade de registros, não.
  Future<List<JsonMap>> listAll(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final collected = <JsonMap>[];
    var page = 1;
    while (collected.length < maximumCollectionSize) {
      final response = await api.get(
        path,
        query: {...?query, 'page': page},
        accessToken: accessToken,
      );
      final results = ((response['results'] ?? const []) as List)
          .cast<JsonMap>();
      collected.addAll(results);
      if (results.isEmpty || response['next'] == null) break;
      page += 1;
    }
    return collected;
  }

  Future<JsonMap> get(String path) => api.get(path, accessToken: accessToken);

  Future<JsonMap> post(String path, JsonMap body) =>
      api.post(path, body: body, accessToken: accessToken);

  Future<JsonMap> patch(String path, JsonMap body) =>
      api.patch(path, body: body, accessToken: accessToken);

  Future<JsonMap> delete(String path, [JsonMap? body]) =>
      api.delete(path, body: body, accessToken: accessToken);
}
