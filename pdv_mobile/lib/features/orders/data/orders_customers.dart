part of 'orders_repository.dart';

/// Os clientes, como o app do garçom precisa deles.
///
/// Vive no repositório do salão, e não em um repositório próprio, porque o que
/// importa aqui é a MAQUINARIA: `read` marca a origem do dado (vivo ou cache) e
/// `mutate` passa pelo gateway, que enfileira quando a rede cai e reaponta para
/// a nuvem quando a loja está fora. Um repositório separado duplicaria isso —
/// e um cadastro feito no salão sem rede sumiria em silêncio.
extension OrdersCustomers on OrdersRepository {
  /// Uma página de clientes. A busca é do SERVIDOR: o salão tem milhares de
  /// clientes e filtrar só a página carregada diria "não existe" para quem
  /// está na página seguinte.
  Future<List<Map<String, dynamic>>> customers({
    String busca = '',
    int pageSize = 30,
  }) async => _rows(
    await read(
      '/customers/',
      query: {
        'restaurant': session.user.restaurantId,
        if (busca.trim().isNotEmpty) 'search': busca.trim(),
        'ordering': 'name',
        'page_size': pageSize,
      },
    ),
  );

  /// Cadastra um cliente. Pelo gateway: sem rede, entra na fila e sai depois.
  Future<Map<String, dynamic>> createCustomer(Map<String, dynamic> corpo) =>
      mutate(
        method: 'POST',
        path: '/customers/',
        kind: 'create_customer',
        summary: 'Novo cliente: ${corpo['name'] ?? ''}',
        body: {'restaurant': session.user.restaurantId, ...corpo},
      );

  Future<Map<String, dynamic>> updateCustomer(
    String id,
    Map<String, dynamic> corpo,
  ) => mutate(
    method: 'PATCH',
    path: '/customers/$id/',
    kind: 'update_customer',
    summary: 'Cliente atualizado: ${corpo['name'] ?? ''}',
    body: corpo,
  );
}
