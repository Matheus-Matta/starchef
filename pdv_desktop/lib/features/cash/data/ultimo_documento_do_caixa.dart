import '../../../core/network/api_client.dart';

/// A sessão da última abertura, ou do último fechamento, de uma estação.
///
/// Para REIMPRIMIR: o papel enroscou, o operador perdeu o relatório assinado.
/// É só leitura — quem imprime é a rota de sempre (`print-document`), e nada
/// aqui toca no caixa.
///
/// Abertura e fechamento são buscas diferentes de propósito: a última sessão
/// aberta pode estar ABERTA ainda, e o relatório de fechamento é o da última
/// que fechou (`status=closed`, pela hora do fechamento).
class UltimoDocumentoDoCaixa {
  UltimoDocumentoDoCaixa(this.api, {required this.accessToken});

  final ApiClient api;
  final String accessToken;

  Future<Map<String, dynamic>?> ultimaAbertura({required String estacao}) =>
      _primeira(estacao, {'ordering': '-opened_at'});

  Future<Map<String, dynamic>?> ultimoFechamento({required String estacao}) =>
      _primeira(estacao, {'status': 'closed', 'ordering': '-closed_at'});

  Future<Map<String, dynamic>?> _primeira(
    String estacao,
    Map<String, String> filtro,
  ) async {
    if (estacao.trim().isEmpty) return null;
    final resposta = await api.get(
      '/cash-register/',
      query: {'cash_station': estacao, 'page_size': '1', ...filtro},
      accessToken: accessToken,
    );
    final lista = (resposta['results'] as List? ?? const [])
        .whereType<Map>()
        .map(Map<String, dynamic>.from);
    return lista.isEmpty ? null : lista.first;
  }
}
