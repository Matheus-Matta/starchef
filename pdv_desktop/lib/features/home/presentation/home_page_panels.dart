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
  String? get orderType;
  String get search;
  set search(String value);
  String? get selectedOrderItemId;
  bool get printingReceipt;
  bool get emittingInvoice;
  FocusNode get catalogSearchFocus;

  List<Map<String, dynamic>> get tables;
  List<Map<String, dynamic>> get commands;
  List<Map<String, dynamic>> get orders;

  Future<void> _configureProduct(Map<String, dynamic> product);
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
    bool automatic,
    Map<String, dynamic>? customer,
    Future<String?>? salePrinter,
  });
  Future<void> _reprintDanfe(Map<String, dynamic> order);

  Widget _catalog() {
    final filteredProducts = visibleProducts;
    return ProductCatalogPanel(
      products: filteredProducts,
      allProducts: products,
      categories: categories,
      selectedCategory: category,
      search: search,
      searchFocusNode: catalogSearchFocus,
      money: _money,
      onSearchChanged: (value) => setState(() => search = value),
      onCategoryChanged: (value) => setState(() => category = value),
      onProductPressed: _configureProduct,
    );
  }

  /// Este pedido é o destino de uma conta agrupada que já foi paga?
  bool get _isPaidMergeTarget {
    final merge = activeOrder?['closing_merge'];
    return merge is Map &&
        merge['role'] == 'target' &&
        merge['status'] == 'paid';
  }

  /// Quanto cada cartão anexado já tem lançado.
  ///
  /// É o número que o cliente confere em voz alta antes de pagar: com quatro
  /// comandas numa conta só, "quanto é a minha?" é a primeira pergunta.
  @override
  Map<String, double> get _totaisPorComanda => {
    for (final comanda in draft.commands)
      '${comanda['id']}': (draft.commandItems['${comanda['id']}'] ?? const [])
          .fold<double>(
            0,
            (soma, item) =>
                soma + (num.tryParse('${item['total_price'] ?? 0}') ?? 0),
          ),
  };

  Widget _cart() => OrderCartPanel(
    selectedItemId: selectedOrderItemId,
    onSelectItem: _selectOrderItem,
    onChangeQuantity: _changeItemQuantity,
    order: activeOrder,
    draftOrderType: _draftIsLive ? draft.orderType : orderType,
    // Enquanto o rascunho vive, ele é a ÚNICA fonte do destino: duas cópias
    // da mesma comanda divergem assim que uma navegação zera só uma delas, e
    // o carrinho passaria a mostrar um cartão que não vai no pedido.
    table: _draftIsLive ? draft.table : selectedTable,
    command: _draftIsLive ? draft.command : selectedCommand,
    customer: _draftIsLive ? draft.customer : selectedCustomer,
    items: _cartItems,
    money: _money,
    // Só no rascunho: com o pedido aberto, `draftTotal` é nulo e o rodapé
    // volta a ler o total do servidor, que é quem conhece taxa e desconto.
    draftTotal: _draftIsLive ? draft.total : null,
    onPickDraftType: _draftIsLive
        ? (tipo) => unawaited(_pickDraftType(tipo))
        : null,
    onAttachCommand: () => unawaited(_attachCommandToDraft()),
    onDetachCommand: _detachCommandFromDraft,
    draftCommands: _draftIsLive ? draft.commands : const [],
    draftCommandTotals: _draftIsLive ? _totaisPorComanda : const {},
    onVoidItem: _voidItem,
    onFinish: widget.controller.session!.user.canProcessPayments
        ? _finishOrder
        : null,
    onSendToKitchen: () => unawaited(_sendPendingFromShortcut()),
    onPrint: _printCustomerReceipt,
    // O botão não some nem fica desabilitado por perfil. A permissão decide
    // apenas se `_cancelOrder` pode seguir direto ou precisa pedir a senha do
    // restaurante para esta operação.
    onCancel: _cancelOrder,
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
