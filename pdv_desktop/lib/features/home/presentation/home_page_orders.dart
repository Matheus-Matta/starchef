// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Histórico de pedidos: consulta, filtros, cache local e a página.
///
/// Os métodos foram MOVIDOS, não reescritos. Só o que a seção usa de fora está
/// declarado abaixo — o resto vem de [_HomePageShared].
mixin _OrdersSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  void _leaveActiveOrder({String? except});
  Future<void> _sweepStaleDrafts();

  List<Map<String, dynamic>> get orders;
  set orders(List<Map<String, dynamic>> value);
  bool get ordersLoading;
  set ordersLoading(bool value);
  bool get ordersPartial;
  set ordersPartial(bool value);
  String get orderStatusFilter;
  set orderStatusFilter(String value);
  String get orderSearch;
  set orderSearch(String value);
  String get orderOrdering;
  set orderOrdering(String value);
  String? get orderTypeFilter;
  set orderTypeFilter(String? value);
  DateTimeRange? get orderDateRange;
  set orderDateRange(DateTimeRange? value);
  Timer? get ordersSearchDebounce;
  set ordersSearchDebounce(Timer? value);
  TextEditingController get ordersSearchController;
  FocusNode get ordersSearchFocus;

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  set selectedTable(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCommand;
  set selectedCommand(Map<String, dynamic>? value);
  String? get orderType;
  set orderType(String? value);
  List<Map<String, dynamic>> get orderItems;
  set orderItems(List<Map<String, dynamic>> value);
  List<Map<String, dynamic>> get tables;
  String get flowStep;
  set flowStep(String value);

  List<Map<String, dynamic>> get commands;
  Map<String, dynamic>? get selectedCustomer;
  set selectedCustomer(Map<String, dynamic>? value);

  Future<void> _paymentDialog();
  Future<void> _refreshOrder();
  Future<void> _ensureCommandTable();
  Future<void> _printCustomerReceipt([Map<String, dynamic>? target]);
  Widget _operationStat(String label, String value, IconData icon);

  /// Página de pedidos guardada localmente.
  ///
  /// A listagem já vem com os itens de cada pedido, então uma página é a
  /// cópia completa do que dá para editar offline. 50 é um meio-termo: cobre
  /// o movimento recente sem transferir centenas de pedidos com todos os
  /// itens aninhados a cada abertura do PDV.
  static const _ordersPageSize = 50;

  /// Consulta fixa de aquecimento do cache.
  ///
  /// Não leva filtro nenhum de propósito: o cache do `ApiClient` é gravado por
  /// consulta exata, então esta precisa ser sempre a mesma para que exista uma
  /// lista guardada quando a rede cair. Os filtros da tela usam
  /// [_ordersServerQuery], que é outra consulta.
  Map<String, dynamic> get _ordersQuery => {
    'page_size': _ordersPageSize,
    'ordering': '-updated_at',
    'restaurant': restaurantId,
  };

  /// Consulta da tela de Pedidos, com os filtros do operador.
  ///
  /// Manda para a API o que ela sabe filtrar (busca, tipo, período,
  /// ordenação), para que a procura alcance o histórico inteiro e não só a
  /// página que já foi baixada. O agrupamento de situação continua sendo
  /// refinado na memória por [_matchesStatusFilter] — "pendentes" cruza
  /// `status` e `payment_status`, o que a API não expressa num parâmetro só.
  Map<String, dynamic> get _ordersServerQuery {
    final query = <String, dynamic>{
      'page_size': _ordersPageSize,
      'ordering': orderOrdering,
      'restaurant': restaurantId,
    };
    final term = orderSearch.trim();
    if (term.isNotEmpty) query['search'] = term;
    if (orderTypeFilter != null) query['order_type'] = orderTypeFilter;
    if (orderStatusFilter == 'pending') {
      query['payment_pending'] = true;
    } else if (orderStatusFilter != 'all') {
      query['status'] = orderStatusFilter;
    }
    final range = orderDateRange;
    if (range != null) {
      query['opened_after'] = _isoDate(range.start);
      query['opened_before'] = _isoDate(range.end);
    }
    return query;
  }

  static String _isoDate(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  /// Agrupamento de situação escolhido no seletor da tela.
  bool _matchesStatusFilter(Map<String, dynamic> order) {
    switch (orderStatusFilter) {
      case 'all':
        return true;
      case 'pending':
        return order['payment_status'] != 'paid' &&
            {'open', 'awaiting_payment'}.contains('${order['status']}');
      default:
        return '${order['status']}' == orderStatusFilter;
    }
  }

  /// Filtro local, usado quando a busca não alcançou o servidor.
  bool _matchesLocalFilters(Map<String, dynamic> order) {
    if (!_matchesStatusFilter(order)) return false;
    if (orderTypeFilter != null &&
        '${order['order_type']}' != orderTypeFilter) {
      return false;
    }
    final range = orderDateRange;
    if (range != null) {
      final openedAt = DateTime.tryParse('${order['opened_at'] ?? ''}');
      if (openedAt == null) return false;
      final day = DateTime(openedAt.year, openedAt.month, openedAt.day);
      final start = DateTime(
        range.start.year,
        range.start.month,
        range.start.day,
      );
      final end = DateTime(range.end.year, range.end.month, range.end.day);
      if (day.isBefore(start) || day.isAfter(end)) return false;
    }
    final term = orderSearch.trim().toLowerCase();
    if (term.isEmpty) return true;
    final haystack =
        '${order['sequence'] ?? ''} ${order['customer_name'] ?? ''} '
                '${order['table_number'] ?? ''} ${order['command_code'] ?? ''}'
            .toLowerCase();
    return haystack.contains(term);
  }

  /// Ordena a lista local pelo mesmo critério pedido ao servidor.
  List<Map<String, dynamic>> _sortedLocally(List<Map<String, dynamic>> list) {
    final descending = orderOrdering.startsWith('-');
    final field = descending ? orderOrdering.substring(1) : orderOrdering;
    final sorted = [...list];
    sorted.sort((a, b) {
      final comparison = switch (field) {
        'total' => _number(a['total']).compareTo(_number(b['total'])),
        'sequence' => _number(a['sequence']).compareTo(_number(b['sequence'])),
        'opened_at' => '${a['opened_at'] ?? ''}'.compareTo(
          '${b['opened_at'] ?? ''}',
        ),
        _ => '${a['updated_at'] ?? ''}'.compareTo('${b['updated_at'] ?? ''}'),
      };
      return descending ? -comparison : comparison;
    });
    return sorted;
  }

  Future<void> _openOrders() async {
    _leaveActiveOrder();
    await _sweepStaleDrafts();
    if (!mounted) return;
    setState(() {
      flowStep = 'orders';
      activeOrder = null;
      ordersLoading = orders.isEmpty;
    });
    await _reloadOrders();
  }

  /// Busca a lista com os filtros atuais.
  ///
  /// Quem responde é o servidor, sempre. A lista que o operador vê é a que
  /// existe de verdade — inclusive os pedidos abertos em outro caixa, que uma
  /// cópia local deste terminal nunca teria.
  Future<void> _reloadOrders() async {
    try {
      final loaded = await _list('/orders/', query: _ordersServerQuery);
      orders = loaded
          .where((item) => '${item['restaurant']}' == restaurantId)
          .where(_matchesStatusFilter)
          .toList();
      ordersPartial = false;
    } catch (error) {
      if (mounted) {
        orders = [];
        ordersPartial = false;
        _error(error);
      }
    } finally {
      if (mounted) setState(() => ordersLoading = false);
    }
  }

  /// Reaplica os filtros. A busca por texto espera o operador parar de digitar
  /// para não disparar uma requisição por tecla.
  void _onOrdersFilterChanged({bool debounce = false}) {
    ordersSearchDebounce?.cancel();
    if (!debounce) {
      setState(() => ordersLoading = orders.isEmpty);
      unawaited(_reloadOrders());
      return;
    }
    ordersSearchDebounce = Timer(
      const Duration(milliseconds: 400),
      () => unawaited(_reloadOrders()),
    );
  }

  /// Carrega o pedido para edição/pagamento.
  ///
  /// Sempre pela rota de detalhe: a entrada da listagem pode ter envelhecido
  /// entre abrir a tela e escolher a linha, e um item lançado em outro caixa
  /// nesse intervalo não pode sumir do papel por causa disso.
  Future<Map<String, dynamic>?> _orderDetail(
    Map<String, dynamic> fromList,
  ) async {
    final id = '${fromList['id'] ?? ''}';
    try {
      return await api.get('/orders/$id/', accessToken: token);
    } catch (error) {
      if (mounted) _error(error);
      return null;
    }
  }

  Future<void> _editOrder(Map<String, dynamic> order) async {
    final detail = await _orderDetail(order);
    if (detail == null) return;
    activeOrder = detail;
    orderType = '${detail['order_type']}';
    selectedTable = detail['table'] == null
        ? null
        : tables.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '${detail['table']}',
            orElse: () => null,
          );
    selectedCommand = detail['command'] == null
        ? null
        : commands.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '${detail['command']}',
            orElse: () => null,
          );
    selectedCustomer = detail['customer'] == null
        ? null
        : {
            'id': detail['customer'],
            'name': detail['customer_name'] ?? 'Cliente',
            'document': detail['customer_document'],
            'phone': '',
          };
    await _refreshOrder();
    if (mounted) setState(() => flowStep = 'order');
    // Editar um pedido de comanda também é hora de perguntar a mesa: a
    // comanda pode ter sido aberta avulsa e o cliente já ter sentado.
    await _ensureCommandTable();
  }

  Future<void> _payOrder(Map<String, dynamic> order) async {
    final detail = await _orderDetail(order);
    if (detail == null) return;
    activeOrder = detail;
    orderType = '${detail['order_type']}';
    await _paymentDialog();
  }

  /// Barra de busca, filtros e ordenação da tela de Pedidos.
}
