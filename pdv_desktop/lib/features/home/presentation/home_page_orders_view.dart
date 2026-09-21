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

  Future<void> _reloadOrders();
  bool _matchesStatusFilter(Map<String, dynamic> order);
  void _onOrdersFilterChanged({bool debounce});
  Future<void> _editOrder(Map<String, dynamic> order);
  Future<void> _payOrder(Map<String, dynamic> order);
  Future<void> _printCustomerReceipt([Map<String, dynamic>? selectedOrder]);

  static const _filterWidth = 220.0;
  static const _filterHeight = 48.0;

  static Widget _filter(Widget child) =>
      SizedBox(width: _filterWidth, height: _filterHeight, child: child);

  // O rótulo flutuante ocupa parte da altura do InputDecorator. Sem padding
  // vertical próprio, a borda do select fica menor que a busca e o botão.
  static const _selectPadding = EdgeInsets.symmetric(
    horizontal: 10,
    vertical: 12,
  );
  static const _filterConstraints = BoxConstraints(minHeight: _filterHeight);

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
      spacing: 8,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        _filter(
          TextField(
            controller: ordersSearchController,
            focusNode: ordersSearchFocus,
            decoration: InputDecoration(
              constraints: _filterConstraints,
              prefixIcon: const Icon(Icons.search_rounded),
              hintText: 'Pedido, cliente ou mesa',
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
        _filter(
          DropdownButtonFormField<String>(
            key: ValueKey('status-$orderStatusFilter'),
            initialValue: orderStatusFilter,
            // Sem `isExpanded` o rótulo selecionado usa a largura natural do
            // texto e estoura a caixa — "Pendentes de pagamento" não cabe em
            // 220 px com o texto ampliado.
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Situação',
              contentPadding: _selectPadding,
              constraints: _filterConstraints,
            ),
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
        _filter(
          DropdownButtonFormField<String?>(
            key: ValueKey('type-$orderTypeFilter'),
            initialValue: orderTypeFilter,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Tipo',
              contentPadding: _selectPadding,
              constraints: _filterConstraints,
            ),
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
        _filter(
          DropdownButtonFormField<String>(
            key: ValueKey('ordering-$orderOrdering'),
            initialValue: orderOrdering,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Ordenar por',
              contentPadding: _selectPadding,
              constraints: _filterConstraints,
            ),
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
        // SÓ O ÍCONE.
        //
        // Era o único item com rótulo depois de quatro campos rotulados, e o
        // texto "Limpar filtros" pesava mais na barra do que a ação merece —
        // ela só existe quando há filtro aplicado.
        if (hasFilters)
          SizedBox(
            width: _filterHeight,
            height: _filterHeight,
            child: IconButton.outlined(
              tooltip: 'Limpar filtros',
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
            ),
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

  /// Menu compacto de período, inclusive a escolha personalizada.
  Widget _ordersDateRangeMenu(String label) {
    return _filter(
      Align(
        alignment: Alignment.centerLeft,
        child: OrdersDateRangeMenu(
          label: label,
          range: orderDateRange,
          onChanged: (range) {
            setState(() => orderDateRange = range);
            _onOrdersFilterChanged();
          },
        ),
      ),
    );
  }

  Widget _ordersPage() {
    // A lista já vem filtrada do servidor (ou do cache, offline). Aqui só
    // sobra a situação, que cruza dois campos e por isso é decidida sempre
    // localmente — inclusive sobre o resultado do servidor.
    final filtered = orders.where(_matchesStatusFilter).toList();
    // Os três cartões de contagem que ficavam aqui saíram. Eles ocupavam a
    // faixa mais nobre da tela — a primeira que se olha — para dizer o que a
    // própria lista já mostra, e o espaço deles é linha de pedido.
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _ordersFilterBar(),
          if (ordersPartial) ...[
            const SizedBox(height: 12),
            _ordersPartialWarning(),
          ],
          const SizedBox(height: 10),
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
                        // A linha da tabela vem do tema, e quantas cabem
                        // vem de `OrdersTableMetrics` — que existe justamente
                        // para essa conta poder ser testada.
                        const rowHeight = AppTheme.tableRowHeight;
                        final rowsPerPage = OrdersTableMetrics.rowsThatFit(
                          constraints.maxHeight,
                        );
                        return SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: SizedBox(
                            width: constraints.maxWidth < 1000
                                ? 1000
                                : constraints.maxWidth,
                            child: PaginatedDataTable(
                              // Sem título: a contagem que ficava aqui é a
                              // mesma que a paginação mostra logo abaixo, e a
                              // faixa do título custava 64 px de altura que
                              // agora são duas linhas de pedido.
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
