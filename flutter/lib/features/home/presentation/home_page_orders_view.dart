// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// A tela de Pedidos: barra de filtros, intervalo de datas e a lista.
///
/// Separada da consulta (`_OrdersSection`) pelo mesmo motivo do pagamento:
/// filtro e cache mudam por regra, a tela muda por desenho.
mixin _OrdersView on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  List<Map<String, dynamic>> get orders;
  bool get ordersLoading;
  bool get ordersPartial;
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
  TextEditingController get ordersSearchController;
  FocusNode get ordersSearchFocus;
  bool get isSecondaryStation;

  Future<void> _reloadOrders();
  bool _matchesStatusFilter(Map<String, dynamic> order);
  void _onOrdersFilterChanged({bool debounce});
  Future<void> _editOrder(Map<String, dynamic> order);
  Future<void> _payOrder(Map<String, dynamic> order);
  Future<void> _printCustomerReceipt([Map<String, dynamic>? selectedOrder]);
  Widget _operationStat(String label, String value, IconData icon);

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

    // O SELETOR DE PERÍODO É UM CAMPO, não um botão.
    //
    // Ele fica na mesma barra do campo de busca e de três selects, todos
    // desenhados como `InputDecorator`. Um `OutlinedButton` ali tem outra
    // altura, outra borda e nenhum rótulo — e a linha inteira saía em
    // escadinha. Vestindo a mesma decoração, ele passa a medir o mesmo que os
    // vizinhos sem ninguém precisar acertar pixels à mão.
    return MenuAnchor(
      builder: (context, controller, child) => InkWell(
        onTap: () => controller.isOpen ? controller.close() : controller.open(),
        borderRadius: AppTheme.radius,
        child: InputDecorator(
          decoration: const InputDecoration(
            labelText: 'Período',
            prefixIcon: Icon(Icons.date_range_outlined, size: 18),
          ),
          child: Text(label, maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
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
                        // Precisa ser a MESMA altura que a tabela usa de
                        // fato: ela não rola internamente, então uma conta
                        // feita com altura menor que a real deixa a tabela
                        // mais alta que o espaço disponível e estoura. Por
                        // isso lê o tema em vez de repetir um número aqui.
                        const rowHeight = AppTheme.tableRowHeight;
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
                              dataRowMinHeight: rowHeight,
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
