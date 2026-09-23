part of 'orders_repository.dart';

extension OrdersQueries on OrdersRepository {
  static const _pageSize = 30;
  static const _openStatuses = ['open', 'awaiting_payment'];

  Future<List<Map<String, dynamic>>> openOrders() async {
    final merged = <String, Map<String, dynamic>>{};
    for (final status in _openStatuses) {
      final page = await read(
        '/orders/',
        query: {
          'status': status,
          'restaurant': session.user.restaurantId,
          'ordering': '-opened_at',
          'page_size': 50,
        },
      );
      for (final order in _rows(page)) {
        merged['${order['id']}'] = order;
      }
    }
    final orders = merged.values.toList();
    orders.sort(
      (a, b) => '${b['opened_at'] ?? ''}'.compareTo('${a['opened_at'] ?? ''}'),
    );
    return orders;
  }

  Future<Map<String, dynamic>> order(String id) => read('/orders/$id/');

  /// As comandas EM USO do salão, para a tela inicial.
  ///
  /// "Em uso" é um estado que o backend mantém no primeiro lançamento, e ele
  /// vem filtrado de lá de propósito: um salão tem centenas de cartões e só
  /// alguns em atendimento — trazer todos para filtrar aqui gastaria a rede do
  /// salão para jogar quase tudo fora.
  ///
  /// `pending_items` e `pending_total` já vêm na listagem, então o cartão
  /// mostra quanto a comanda deve sem abrir uma por uma.
  Future<List<Map<String, dynamic>>> commandsInUse() async {
    final rows = _rows(
      await read(
        '/commands/',
        query: {
          'restaurant': session.user.restaurantId,
          'status': 'occupied',
          'is_active': true,
          'ordering': 'number',
          'page_size': 100,
        },
      ),
    );
    return commandsWithPendingItems(rows);
  }

  /// O que a comanda tem AGORA — as anotações pendentes.
  ///
  /// Não é `command.items`, que devolve o histórico INTEIRO do cartão: a
  /// comanda reutilizada apareceria cheia com a conta do cliente anterior.
  Future<Map<String, dynamic>> commandItems(String commandId) =>
      read('/commands/$commandId/items/');

  Future<List<Map<String, dynamic>>> tables() async => _rows(
    await read(
      '/tables/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'page_size': 100,
        'ordering': 'number',
      },
    ),
  );

  Future<ResourcePage> commands({int page = 1, String search = ''}) async {
    final response = await read(
      '/commands/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'ordering': 'number',
        'page': page,
        'page_size': _pageSize,
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    return ResourcePage.from(response);
  }

  Future<ResourcePage> products({int page = 1, String search = ''}) async {
    final response = await read(
      '/menu/products/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'ordering': 'name',
        'page': page,
        'page_size': _pageSize,
        if (search.trim().isNotEmpty) 'search': search.trim(),
      },
    );
    return ResourcePage.from(response);
  }

  Future<List<Map<String, dynamic>>> paymentMethods() async => _rows(
    await read(
      '/payments/methods/',
      query: {
        'restaurant': session.user.restaurantId,
        'is_active': true,
        'page_size': 100,
      },
    ),
  );

  Future<List<Map<String, dynamic>>> payments(String orderId) async =>
      _rows(await read('/orders/$orderId/payments/'));

  Future<Map<String, dynamic>?> currentCashRegister() async {
    try {
      final response = await read(
        '/cash-register/current/',
        query: {'restaurant': session.user.restaurantId},
      );
      return '${response['id'] ?? ''}'.isEmpty ? null : response;
    } on ApiException {
      return null;
    }
  }
}
