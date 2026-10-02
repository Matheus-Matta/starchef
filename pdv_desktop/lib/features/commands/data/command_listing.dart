import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';

/// Lista de comandas, página por página até o fim.
///
/// A rota limita a página a 100. Pedir `page_size=200` e ler só a primeira
/// resposta deixava a tela de comandas mostrando as 100 primeiras de uma loja
/// com 500 cartões — o resto simplesmente não existia para o PDV.
Future<List<Map<String, dynamic>>> listarComandas(
  ApiClient api, {
  String? accessToken,
  String? restaurantId,
  int? numeroMinimo,
  int? numeroMaximo,
  int limite = 5000,
}) async {
  final todas = <Map<String, dynamic>>[];
  for (var pagina = 1; todas.length < limite; pagina++) {
    final resposta = await api.get(
      '/commands/',
      query: {
        'page_size': 100,
        'page': pagina,
        'is_active': true,
        'ordering': 'number',
        if (restaurantId != null && restaurantId.isNotEmpty)
          'restaurant': restaurantId,
        'number_min': ?numeroMinimo,
        'number_max': ?numeroMaximo,
      },
      accessToken: accessToken,
    );
    // `results` é a resposta paginada; `data` e a lista crua cobrem uma rota
    // sem paginação. Nenhum dos três sendo lista, a resposta não é o que esta
    // tela sabe ler — e devolver vazio em silêncio faria a página parecer que
    // não tem comanda nenhuma, quando o que houve foi um formato inesperado.
    final bruto = resposta['results'] ?? resposta['data'] ?? const [];
    if (bruto is! List) {
      throw ApiException(
        'O servidor respondeu num formato que esta tela não reconhece.',
      );
    }
    todas.addAll(bruto.whereType<Map>().map(Map<String, dynamic>.from));
    if (bruto.isEmpty || resposta['next'] == null) break;
  }
  return todas;
}
