/// Uma página da API (DRF): as linhas e se ainda há mais para buscar.
///
/// Fica no núcleo porque é o tipo que atravessa as camadas: o repositório
/// devolve, e a lista com rolagem infinita (`PaginatedPicker`) consome.
/// Enquanto morava só no repositório, a lista declarava um registro
/// equivalente e cada tela convertia um no outro na mão.
class ResourcePage {
  const ResourcePage({required this.rows, required this.hasMore});

  final List<Map<String, dynamic>> rows;
  final bool hasMore;

  static ResourcePage from(Map<String, dynamic> payload) {
    final results = payload['results'];
    return ResourcePage(
      rows: results is List
          ? results.whereType<Map>().map(Map<String, dynamic>.from).toList()
          : const [],
      // `next` nulo é o fim da lista — é o próprio DRF dizendo, sem o app ter
      // de adivinhar por contagem.
      hasMore: payload['next'] != null,
    );
  }
}
