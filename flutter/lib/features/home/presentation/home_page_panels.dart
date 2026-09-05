// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Painéis da tela de vendas: início, catálogo e carrinho.
///
/// O código foi MOVIDO, não reescrito.
mixin _PanelsSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get selectedCustomer;
  Map<String, dynamic>? get cashSession;
  List<Map<String, dynamic>> get orderItems;
  List<Map<String, dynamic>> get products;
  List<Map<String, dynamic>> get categories;
  List<Map<String, dynamic>> get visibleProducts;
  String? get category;
  set category(String? value);
  String get search;
  set search(String value);
  String? get selectedOrderItemId;
  bool get printingReceipt;
  bool get emittingInvoice;

  List<Map<String, dynamic>> get tables;
  List<Map<String, dynamic>> get commands;
  List<Map<String, dynamic>> get orders;

  Future<void> _configureProduct(Map<String, dynamic> product);
  Future<void> _selectOrderType(String type);
  void _selectOrderItem(Map<String, dynamic> item);
  Future<void> _changeItemQuantity(Map<String, dynamic> item, int delta);
  Future<void> _voidItem(Map<String, dynamic> item);
  Future<void> _finishOrder();
  Future<void> _sendPendingFromShortcut();
  Future<void> _printCustomerReceipt([Map<String, dynamic>? selectedOrder]);
  Future<void> _cancelOrder();
  Future<void> _emitFiscalInvoice(
    Map<String, dynamic> order, {
    bool silentIfUnconfigured,
  });
  Future<void> _reprintDanfe(Map<String, dynamic> order);

  Widget _startPanel() {
    final options = [
      (
        'command',
        'Comanda',
        'Atendimento no salão ou cartão de comanda',
        Icons.qr_code_2,
      ),
      ('counter', 'Balcão', 'Consumo rápido no local', Icons.storefront),
      (
        'takeaway',
        'Retirada',
        'Pedido para viagem',
        Icons.shopping_bag_outlined,
      ),
      ('delivery', 'Delivery', 'Pedido para entrega', Icons.delivery_dining),
    ];
    final scheme = Theme.of(context).colorScheme;
    final availableTables = tables
        .where(
          (item) =>
              (item['active_commands'] as List? ?? const []).isEmpty &&
              item['status'] == 'free',
        )
        .length;
    final availableCommands = commands
        .where(
          (item) =>
              item['is_active'] != false &&
              item['status'] == 'free' &&
              item['current_order_id'] == null,
        )
        .length;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Escolha o tipo de atendimento',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              AppStatusBadge(
                label: '${products.length} produtos ativos',
                icon: Icons.inventory_2_outlined,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _operationStat(
                  'MESAS LIVRES',
                  '$availableTables',
                  Icons.table_restaurant_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _operationStat(
                  'COMANDAS LIVRES',
                  '$availableCommands',
                  Icons.qr_code_2_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _operationStat(
                  'PEDIDOS CARREGADOS',
                  '${orders.length}',
                  Icons.receipt_long_outlined,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Divider(height: 1, color: scheme.outlineVariant),
          const SizedBox(height: 14),
          Expanded(
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 230,
                mainAxisExtent: 190,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
              ),
              itemCount: options.length,
              itemBuilder: (_, index) {
                final option = options[index];
                return ShadCard(
                  padding: EdgeInsets.zero,
                  radius: AppTheme.radius,
                  shadows: const [],
                  columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      borderRadius: AppTheme.radius,
                      onTap: () => _selectOrderType(option.$1),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Container(height: 3, color: scheme.primary),
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Container(
                                        width: 42,
                                        height: 42,
                                        decoration: BoxDecoration(
                                          color: scheme.primaryContainer,
                                          borderRadius: AppTheme.radius,
                                        ),
                                        child: Icon(
                                          option.$4,
                                          color: scheme.primary,
                                          size: 21,
                                        ),
                                      ),
                                      const Spacer(),
                                      Text(
                                        '${index + 1}'.padLeft(2, '0'),
                                        style: TextStyle(
                                          color: scheme.onSurfaceVariant,
                                          fontSize: 10,
                                          fontWeight: FontWeight.w900,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const Spacer(),
                                  Text(
                                    option.$2,
                                    style: const TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.w900,
                                    ),
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    option.$3,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: scheme.onSurfaceVariant,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  Row(
                                    children: [
                                      Text(
                                        'INICIAR',
                                        style: TextStyle(
                                          color: scheme.primary,
                                          fontSize: 9,
                                          fontWeight: FontWeight.w900,
                                          letterSpacing: .8,
                                        ),
                                      ),
                                      const Spacer(),
                                      Icon(
                                        Icons.arrow_forward,
                                        size: 16,
                                        color: scheme.primary,
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _operationStat(String label, String value, IconData icon) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 72,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: AppTheme.radius,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(icon, size: 19, color: scheme.onSurfaceVariant),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 8,
                    fontWeight: FontWeight.w900,
                    letterSpacing: .5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _catalog() {
    final filteredProducts = visibleProducts;
    return ProductCatalogPanel(
      products: filteredProducts,
      allProducts: products,
      categories: categories,
      selectedCategory: category,
      search: search,
      money: _money,
      onSearchChanged: (value) => setState(() => search = value),
      onCategoryChanged: (value) => setState(() => category = value),
      onProductPressed: _configureProduct,
    );
  }

  Widget _cart() => OrderCartPanel(
    selectedItemId: selectedOrderItemId,
    onSelectItem: _selectOrderItem,
    onChangeQuantity: _changeItemQuantity,
    order: activeOrder,
    table: selectedTable,
    command: selectedCommand,
    customer: selectedCustomer,
    items: orderItems,
    money: _money,
    onVoidItem: _voidItem,
    onFinish: widget.controller.session!.user.canProcessPayments
        ? _finishOrder
        : null,
    onSendToKitchen: () => unawaited(_sendPendingFromShortcut()),
    onPrint: _printCustomerReceipt,
    onCancel: widget.controller.session!.user.canCancelOrders
        ? _cancelOrder
        : null,
    onEmitInvoice:
        activeOrder == null ||
            !widget.controller.session!.user.canProcessPayments
        ? null
        : () => _emitFiscalInvoice(activeOrder!),
    onPrintInvoice:
        activeOrder == null ||
            !widget.controller.session!.user.canProcessPayments
        ? null
        : () => _reprintDanfe(activeOrder!),
    printing: printingReceipt,
    emittingInvoice: emittingInvoice,
  );
}
