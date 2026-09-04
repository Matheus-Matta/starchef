part of 'home_page.dart';

/// Histórico de pedidos: consulta, filtros, cache local e a página.
///
/// Os métodos foram MOVIDOS, não reescritos. Só o que a seção usa de fora está
/// declarado abaixo — o resto vem de [_HomePageShared].
mixin _OrdersSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalOrderStore get orderStore;

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
  bool get isSecondaryStation;

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

  /// Baixa e guarda os pedidos recentes sem prender a interface.
  Future<void> _warmOrdersCache() async {
    if (restaurantId == null) return;
    try {
      await api.get('/orders/', query: _ordersQuery, accessToken: token);
    } catch (_) {
      // É só aquecimento de cache: sem rede, o que já estiver guardado serve,
      // e a tela de Pedidos reporta o problema quando for aberta.
    }
  }

  Future<void> _openOrders() async {
    final scope = api.sessionScope;
    // Abre já com o que está guardado: a lista aparece na hora e a versão do
    // servidor entra por cima quando chegar. Só mostra "carregando" quem
    // ainda não tem nada para ver.
    final cached = scope == null ? const <Map<String, dynamic>>[] : null;
    final local = cached ?? await _ordersFromStore(scope!);
    if (!mounted) return;
    setState(() {
      flowStep = 'orders';
      activeOrder = null;
      if (local.isNotEmpty) orders = _localResults(local);
      ordersLoading = orders.isEmpty;
    });
    await _reloadOrders();
  }

  /// Busca a lista com os filtros atuais.
  ///
  /// A consulta é servida pelo armazenamento local (§3), que já traz tanto os
  /// pedidos confirmados quanto os que ainda estão na fila — não há mais o
  /// vai-e-vem de "buscar no servidor, gravar, reler de cada pedido" que
  /// existia para não apagar da tela um lançamento offline.
  Future<void> _reloadOrders() async {
    final scope = api.sessionScope;
    try {
      final loaded = await _list('/orders/', query: _ordersServerQuery);
      orders = loaded
          .where((item) => '${item['restaurant']}' == restaurantId)
          .where(_matchesStatusFilter)
          .toList();
      // Sem conexão, um pedido antigo pode simplesmente ainda não ter descido
      // para este terminal. A lista continua útil — o operador precisa achar o
      // pedido aberto agora —, mas a tela avisa que pode faltar algo.
      ordersPartial = !api.syncStatus.hasConnection;
    } catch (error) {
      final localCopy = scope == null
          ? const <Map<String, dynamic>>[]
          : await _ordersFromStore(scope);
      if (localCopy.isNotEmpty) {
        orders = _localResults(localCopy);
        ordersPartial = true;
      } else if (mounted) {
        orders = [];
        ordersPartial = false;
        _error(error);
      }
    } finally {
      if (mounted) setState(() => ordersLoading = false);
    }
  }

  List<Map<String, dynamic>> _localResults(List<Map<String, dynamic>> source) =>
      _sortedLocally(source.where(_matchesLocalFilters).toList());

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

  Future<List<Map<String, dynamic>>> _ordersFromStore(String scope) async {
    await _reconcileLocalIds(scope);
    final stored = await orderStore.recent(
      scope: scope,
      limit: _ordersPageSize,
    );
    return stored
        .where((item) => '${item['restaurant']}' == restaurantId)
        .toList();
  }

  Future<void> _reconcileLocalIds(String scope) async {
    final mappings = await api.resolvedTemporaryIds();
    for (final entry in mappings.entries) {
      await orderStore.replaceId(entry.key, entry.value, scope: scope);
    }
  }

  /// Carrega o pedido para edição/pagamento, com o que houver disponível.
  ///
  /// A listagem já traz o pedido completo — o serializer aninha os itens —,
  /// então [fromList] é uma cópia legítima do detalhe, e não um resumo. Sem
  /// rede, ela é a fonte: antes o operador não conseguia abrir um pedido que
  /// não tivesse sido feito neste terminal, porque só a rota de detalhe tinha
  /// sido cacheada e ela nunca fora chamada para aquele pedido.
  Future<Map<String, dynamic>?> _orderDetail(
    Map<String, dynamic> fromList,
  ) async {
    final id = '${fromList['id'] ?? ''}';
    final scope = api.sessionScope;

    // Um pedido criado offline só existe localmente; buscá-lo no servidor
    // devolveria 404.
    if (id.startsWith('offline-') && scope != null) {
      final local = await orderStore.read(id, scope: scope);
      if (local != null) return local;
    }

    try {
      final fresh = await api.get('/orders/$id/', accessToken: token);
      if (scope != null) {
        // Guardar aqui preserva os itens lançados offline que o servidor
        // ainda não conhece.
        return await orderStore.saveFromServer(fresh, scope: scope);
      }
      return fresh;
    } on ApiException catch (error) {
      if (!error.isConnectivity) {
        if (mounted) _error(error);
        return null;
      }
      // A cópia local vem antes da entrada da listagem porque é ela que tem
      // as edições feitas sem rede.
      final local = scope == null
          ? null
          : await orderStore.read(id, scope: scope);
      final fallback = local ?? (fromList['items'] is List ? fromList : null);
      if (fallback != null) {
        if (mounted) _warnLocalOrderData();
        return fallback;
      }
      if (mounted) {
        _error(
          error,
          title: 'Este pedido ainda não está salvo neste terminal',
          action:
              'Abra a tela de Pedidos com a rede disponível ao menos uma vez '
              'para guardar os dados; depois ele funciona offline.',
        );
      }
      return null;
    } catch (error) {
      if (mounted) _error(error);
      return null;
    }
  }

  /// Avisa que a edição está usando a cópia local, uma vez por queda de rede.
  void _warnLocalOrderData() {
    ErrorCenterScope.read(context).report(
      AppError(
        title: 'Editando com os dados salvos localmente',
        message:
            'Sem conexão, este pedido é aberto a partir da última cópia '
            'guardada neste terminal. Se ele foi alterado em outro caixa, '
            'essas mudanças ainda não aparecem aqui.',
        origin: AppErrorOrigin.network,
        severity: AppErrorSeverity.warning,
        recommendedAction:
            'As alterações feitas agora entram na fila e sobem quando a rede '
            'voltar.',
        dedupeKey: 'order-local-copy',
      ),
    );
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
  Widget _ordersFilterBar() {
    final range = orderDateRange;
    final dateLabel = range == null
        ? 'Período'
        : '${_shortDate(range.start)} – ${_shortDate(range.end)}';
    final hasFilters =
        orderSearch.trim().isNotEmpty ||
        orderTypeFilter != null ||
        orderDateRange != null ||
        orderStatusFilter != 'pending' ||
        orderOrdering != '-updated_at';
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 300,
          child: TextField(
            controller: ordersSearchController,
            focusNode: ordersSearchFocus,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search_rounded),
              hintText: 'Nº do pedido, cliente ou mesa...',
              suffixIcon: orderSearch.isEmpty
                  ? null
                  : IconButton(
                      tooltip: 'Limpar busca',
                      icon: const Icon(Icons.close_rounded, size: 18),
                      onPressed: () {
                        ordersSearchController.clear();
                        setState(() => orderSearch = '');
                        _onOrdersFilterChanged();
                      },
                    ),
            ),
            onChanged: (value) {
              setState(() => orderSearch = value);
              _onOrdersFilterChanged(debounce: true);
            },
          ),
        ),
        SizedBox(
          width: 230,
          child: DropdownButtonFormField<String>(
            initialValue: orderStatusFilter,
            // Sem `isExpanded` o rótulo selecionado usa a largura natural do
            // texto e estoura a caixa — "Pendentes de pagamento" não cabe em
            // 230 px com o texto ampliado.
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Situação'),
            items: const [
              DropdownMenuItem(
                value: 'pending',
                child: Text(
                  'Pendentes de pagamento',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(value: 'open', child: Text('Em aberto')),
              DropdownMenuItem(
                value: 'awaiting_payment',
                child: Text(
                  'Aguardando pagamento',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(value: 'paid', child: Text('Pagos')),
              DropdownMenuItem(value: 'all', child: Text('Todos')),
            ],
            onChanged: (value) {
              setState(() => orderStatusFilter = value ?? 'pending');
              _onOrdersFilterChanged();
            },
          ),
        ),
        SizedBox(
          width: 180,
          child: DropdownButtonFormField<String?>(
            initialValue: orderTypeFilter,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Tipo'),
            items: const [
              DropdownMenuItem(value: null, child: Text('Todos os tipos')),
              DropdownMenuItem(value: 'command', child: Text('Comanda')),
              DropdownMenuItem(value: 'counter', child: Text('Balcão')),
              DropdownMenuItem(value: 'takeaway', child: Text('Retirada')),
              DropdownMenuItem(value: 'delivery', child: Text('Delivery')),
            ],
            onChanged: (value) {
              setState(() => orderTypeFilter = value);
              _onOrdersFilterChanged();
            },
          ),
        ),
        SizedBox(
          width: 210,
          child: DropdownButtonFormField<String>(
            initialValue: orderOrdering,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Ordenar por'),
            items: const [
              DropdownMenuItem(
                value: '-updated_at',
                child: Text(
                  'Última atualização',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(
                value: '-opened_at',
                child: Text(
                  'Abertos recentemente',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(
                value: 'opened_at',
                child: Text('Mais antigos', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '-total',
                child: Text('Maior valor', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: 'total',
                child: Text('Menor valor', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '-sequence',
                child: Text('Nº decrescente', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: 'sequence',
                child: Text('Nº crescente', overflow: TextOverflow.ellipsis),
              ),
            ],
            onChanged: (value) {
              setState(() => orderOrdering = value ?? '-updated_at');
              _onOrdersFilterChanged();
            },
          ),
        ),
        _ordersDateRangeMenu(dateLabel),
        if (hasFilters)
          TextButton.icon(
            onPressed: () {
              ordersSearchController.clear();
              setState(() {
                orderSearch = '';
                orderTypeFilter = null;
                orderDateRange = null;
                orderStatusFilter = 'pending';
                orderOrdering = '-updated_at';
              });
              _onOrdersFilterChanged();
            },
            icon: const Icon(Icons.filter_alt_off_outlined),
            label: const Text('Limpar filtros'),
          ),
      ],
    );
  }

  Widget _ordersPartialWarning() {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: .12),
        borderRadius: AppTheme.radius,
        border: Border.all(color: Colors.orange.withValues(alpha: .4)),
      ),
      child: Row(
        children: [
          Icon(Icons.cloud_off_rounded, size: 18, color: scheme.onSurface),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'Sem conexão: a busca vale só para os pedidos já guardados '
              'neste caixa. Pedidos antigos podem não aparecer.',
            ),
          ),
        ],
      ),
    );
  }

  static String _shortDate(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/'
      '${value.month.toString().padLeft(2, '0')}';

  /// Menu compacto de período, ancorado no botão — em vez do seletor nativo,
  /// que abre um diálogo grande e cobre a tela para escolher só duas datas.
  /// Os atalhos cobrem o uso comum; "Personalizado" ainda cai no seletor
  /// nativo, só para quem realmente precisa de datas específicas.
  Widget _ordersDateRangeMenu(String label) {
    final today = DateTime.now();
    final startOfToday = DateTime(today.year, today.month, today.day);

    DateTimeRange lastDays(int count) => DateTimeRange(
      start: startOfToday.subtract(Duration(days: count - 1)),
      end: startOfToday,
    );

    void apply(DateTimeRange? range) {
      setState(() => orderDateRange = range);
      _onOrdersFilterChanged();
    }

    return MenuAnchor(
      builder: (context, controller, child) => OutlinedButton.icon(
        onPressed: () =>
            controller.isOpen ? controller.close() : controller.open(),
        icon: const Icon(Icons.date_range_outlined),
        label: Text(label),
      ),
      menuChildren: [
        MenuItemButton(
          onPressed: () =>
              apply(DateTimeRange(start: startOfToday, end: startOfToday)),
          child: const Text('Hoje'),
        ),
        MenuItemButton(
          onPressed: () {
            final yesterday = startOfToday.subtract(const Duration(days: 1));
            apply(DateTimeRange(start: yesterday, end: yesterday));
          },
          child: const Text('Ontem'),
        ),
        MenuItemButton(
          onPressed: () => apply(lastDays(7)),
          child: const Text('Últimos 7 dias'),
        ),
        MenuItemButton(
          onPressed: () => apply(lastDays(30)),
          child: const Text('Últimos 30 dias'),
        ),
        MenuItemButton(
          onPressed: () => apply(
            DateTimeRange(
              start: DateTime(today.year, today.month, 1),
              end: startOfToday,
            ),
          ),
          child: const Text('Este mês'),
        ),
        const Divider(height: 1),
        MenuItemButton(
          onPressed: () => unawaited(_pickCustomDateRange()),
          child: const Text('Personalizado...'),
        ),
        if (orderDateRange != null)
          MenuItemButton(
            onPressed: () => apply(null),
            child: const Text('Limpar período'),
          ),
      ],
    );
  }

  Future<void> _pickCustomDateRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 2),
      lastDate: DateTime(now.year + 1),
      initialDateRange: orderDateRange,
      helpText: 'Período de abertura',
      saveText: 'Aplicar',
    );
    if (picked == null || !mounted) return;
    setState(() => orderDateRange = picked);
    _onOrdersFilterChanged();
  }

  Widget _ordersPage() {
    // A lista já vem filtrada do servidor (ou do cache, offline). Aqui só
    // sobra a situação, que cruza dois campos e por isso é decidida sempre
    // localmente — inclusive sobre o resultado do servidor.
    final filtered = orders.where(_matchesStatusFilter).toList();
    final openCount = orders
        .where(
          (item) =>
              const {'open', 'awaiting_payment'}.contains('${item['status']}'),
        )
        .length;
    final paidCount = orders
        .where((item) => '${item['payment_status']}' == 'paid')
        .length;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: _operationStat(
                  'RESULTADOS DO FILTRO',
                  '${filtered.length}',
                  Icons.filter_alt_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _operationStat(
                  'PEDIDOS EM ABERTO',
                  '$openCount',
                  Icons.pending_actions_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _operationStat(
                  'PAGAMENTOS CONCLUÍDOS',
                  '$paidCount',
                  Icons.check_circle_outline,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _ordersFilterBar(),
          if (ordersPartial) ...[
            const SizedBox(height: 12),
            _ordersPartialWarning(),
          ],
          const SizedBox(height: 18),
          Expanded(
            child: ShadCard(
              radius: AppTheme.radius,
              shadows: const [],
              padding: EdgeInsets.zero,
              columnCrossAxisAlignment: CrossAxisAlignment.stretch,
              child: ordersLoading
                  ? const Center(child: CircularProgressIndicator())
                  : filtered.isEmpty
                  ? const AppEmptyState(
                      icon: Icons.receipt_long_outlined,
                      title: 'Nenhum pedido encontrado',
                      description:
                          'Altere os filtros ou atualize a lista para tentar novamente.',
                    )
                  : LayoutBuilder(
                      builder: (context, constraints) {
                        // Precisa ser a mesma altura passada em
                        // dataRowMaxHeight abaixo: a tabela não rola
                        // internamente, então se a conta de quantas linhas
                        // cabem usar uma altura menor que a real, a tabela
                        // fica mais alta que o espaço disponível e estoura.
                        const rowHeight = 68.0;
                        final calculatedRows =
                            ((constraints.maxHeight - 180) / rowHeight).floor();
                        final rowsPerPage = calculatedRows.clamp(1, 10);
                        return SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: SizedBox(
                            width: constraints.maxWidth < 1000
                                ? 1000
                                : constraints.maxWidth,
                            child: PaginatedDataTable(
                              header: Text('${filtered.length} pedido(s)'),
                              // Não há seleção múltipla nessa lista; sem isso
                              // o DataTable mostra uma caixa de marcação por
                              // linha por padrão, sem nenhuma ação associada.
                              showCheckboxColumn: false,
                              // A linha padrão tem 48 px fixos, e a célula de
                              // ações traz botões que passam disso com o texto
                              // ampliado que o PDV usa — daí o estouro de
                              // poucos pixels repetido em toda linha. Dar
                              // altura suficiente resolve na origem, em vez de
                              // encolher os alvos de toque do operador.
                              dataRowMinHeight: 52,
                              dataRowMaxHeight: rowHeight,
                              rowsPerPage: rowsPerPage,
                              availableRowsPerPage: <int>{
                                rowsPerPage,
                                5,
                                10,
                                20,
                              }.toList()..sort(),
                              showFirstLastButtons: true,
                              columns: const [
                                DataColumn(label: Text('Pedido')),
                                DataColumn(label: Text('Tipo')),
                                DataColumn(label: Text('Comanda/Mesa/Cliente')),
                                DataColumn(label: Text('Status')),
                                DataColumn(label: Text('Pagamento')),
                                DataColumn(label: Text('Total')),
                                DataColumn(label: Text('Ações')),
                              ],
                              source: OrderDataSource(
                                filtered,
                                money: _money,
                                onEdit: _editOrder,
                                onPay: _payOrder,
                                onPrint: _printCustomerReceipt,
                                allowEdit: widget
                                    .controller
                                    .session!
                                    .user
                                    .canManageOrders,
                                allowPayment: widget
                                    .controller
                                    .session!
                                    .user
                                    .canProcessPayments,
                              ),
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
