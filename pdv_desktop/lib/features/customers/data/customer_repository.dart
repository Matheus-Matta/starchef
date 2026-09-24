import '../../../core/network/api_client.dart';

/// O cadastro de clientes como o PDV precisa dele.
///
/// A busca é do SERVIDOR, e não da tela: um restaurante com dez mil clientes
/// não cabe na memória do terminal, e filtrar uma página de cinquenta daria a
/// impressão de que o cliente não existe quando ele está na página seguinte.
class CustomerRepository {
  const CustomerRepository(this._api, {required this.accessToken});

  final ApiClient _api;
  final String accessToken;

  /// Uma página de clientes. [busca] vai para o `search` do backend, que já
  /// procura em nome, telefone, e-mail e CPF.
  Future<List<Map<String, dynamic>>> list({
    String? restaurantId,
    String busca = '',
    int pageSize = 50,
  }) async {
    final resposta = await _api.get(
      '/customers/',
      query: {
        'restaurant': ?restaurantId,
        if (busca.trim().isNotEmpty) 'search': busca.trim(),
        'ordering': 'name',
        'page_size': pageSize,
      },
      accessToken: accessToken,
    );
    final resultados = resposta['results'] ?? resposta['data'];
    if (resultados is! List) return const [];
    return resultados
        .whereType<Map>()
        .map(Map<String, dynamic>.from)
        .toList(growable: false);
  }

  Future<Map<String, dynamic>> create(Map<String, dynamic> corpo) =>
      _api.post('/customers/', body: corpo, accessToken: accessToken);

  Future<Map<String, dynamic>> update(String id, Map<String, dynamic> corpo) =>
      _api.patch('/customers/$id/', body: corpo, accessToken: accessToken);

  /// Os grupos, para a tela mostrar de que recortes o cliente participa.
  Future<List<Map<String, dynamic>>> groups() async {
    final resposta = await _api.get(
      '/customers/groups/',
      query: {'is_active': true, 'ordering': 'name', 'page_size': 100},
      accessToken: accessToken,
    );
    final resultados = resposta['results'] ?? resposta['data'];
    if (resultados is! List) return const [];
    return resultados
        .whereType<Map>()
        .map(Map<String, dynamic>.from)
        .toList(growable: false);
  }
}
