import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import 'command_pager.dart';

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

/// Uma página só — é o que a rolagem pede, uma de cada vez.
///
/// Ordenada por número: digitar "12" traz a 12 antes da 112 e da 120, porque
/// a busca do servidor é por "contém" e a exata é sempre a de menor número.
Future<PaginaDeComandas> paginaDeComandas(
  ApiClient api, {
  required int pagina,
  String busca = '',
  String? accessToken,
  String? restaurantId,
  int tamanho = 50,
}) async {
  final resposta = await api.get(
    '/commands/',
    query: {
      'page_size': tamanho,
      'page': pagina,
      'is_active': true,
      'ordering': 'number',
      if (restaurantId != null && restaurantId.isNotEmpty)
        'restaurant': restaurantId,
      if (busca.trim().isNotEmpty) 'search': busca.trim(),
    },
    accessToken: accessToken,
  );
  final bruto = resposta['results'] ?? resposta['data'] ?? const [];
  if (bruto is! List) {
    throw ApiException(
      'O servidor respondeu num formato que esta tela não reconhece.',
    );
  }
  final total = resposta['count'];
  return (
    itens: bruto.whereType<Map>().map(Map<String, dynamic>.from).toList(),
    temMais: resposta['next'] != null,
    total: total is int ? total : null,
  );
}
