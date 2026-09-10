// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O pedido em si: escolher o tipo, o cliente, abrir, lançar item, pesar,
/// cancelar, mandar para a cozinha e fechar.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _OrderSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;
  LocalOrderStore get orderStore;
  TerminalTopology get topology;

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  set selectedTable(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCommand;
  set selectedCommand(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCustomer;
  set selectedCustomer(Map<String, dynamic>? value);
  Map<String, dynamic>? get cashSession;
  String? get orderType;
  set orderType(String? value);
  List<Map<String, dynamic>> get orderItems;
  set orderItems(List<Map<String, dynamic>> value);
  List<Map<String, dynamic>> get commands;
  List<Map<String, dynamic>> get tables;
  String get flowStep;
  set flowStep(String value);
  String get commandSearch;
  set commandSearch(String value);
  String? get selectedOrderItemId;
  set selectedOrderItemId(String? value);
  String? get scanningProductId;
  set scanningProductId(String? value);
  StreamController<void>? get productScanRepeats;
  set productScanRepeats(StreamController<void>? value);
  double get defaultServiceFeePercent;
  bool get isSecondaryStation;

  void _refreshSuggestedPaymentAmount();
  void _warnLocalOrderData();
  List<Map<String, dynamic>> get products;
  Future<void> _paymentDialog();
  Future<Map<String, dynamic>?> _chooseCustomer(String type);
  Future<Map<String, dynamic>> _sendPendingItemsToKitchen(
    List<Map<String, dynamic>> pending,
  );

  Future<void> _selectOrderType(String type) async {
    orderType = type;
    if (type == 'command') {
      setState(() {
        commandSearch = '';
        flowStep = 'context';
      });
      return;
    }
    if (type == 'takeaway' || type == 'delivery') {
      final customer = await _chooseCustomer(type);
      if (customer == null) {
        setState(() => orderType = null);
        return;
      }
      selectedCustomer = customer;
    }
    await _startOrder(type);
  }

  Future<void> _startOrder(String type) async {
    await _work(() async {
      selectedTable = null;
      activeOrder = await api.post(
        '/orders/',
        body: {
          'restaurant': restaurantId,
          'order_type': type,
          if (selectedCustomer != null) 'customer': selectedCustomer!['id'],
        },
        accessToken: token,
      );
      activeOrder = _completeOfflineOrder(activeOrder!, type: type);
      await _refreshOrder();
      flowStep = 'order';
    });
  }

  /// Relê o pedido da fonte operacional local.
  ///
  /// `api.get` é offline-first: responde do SQLite na hora e reconcilia com o
  /// servidor em paralelo (§3). Por isso não há mais dois caminhos aqui — o
  /// pedido criado offline e o pedido vindo do servidor moram no mesmo lugar.
  Future<void> _refreshOrder() async {
    if (activeOrder == null) return;
    try {
      activeOrder = await api.get(
        '/orders/${activeOrder!['id']}/',
        accessToken: token,
      );
    } on ApiException catch (error) {
      if (!error.isConnectivity) rethrow;
      if (mounted) _warnLocalOrderData();
    }
    final items = activeOrder!['items'] as List? ?? [];
    orderItems = items
        .cast<Map<String, dynamic>>()
        .where((item) => item['status'] != OrderItemStatus.legacyVoided)
        .toList();
    // O total pode ter mudado aqui — a taxa de serviço do fechamento chega
    // pela sincronização, e é depois desta leitura que ela aparece.
    if (flowStep == 'payment') _refreshSuggestedPaymentAmount();
    if (mounted) setState(() {});
  }

  bool _isOfflinePending(Map<String, dynamic>? value) =>
      OrderPresenter.isOffline(value);

  Map<String, dynamic> _completeOfflineOrder(
    Map<String, dynamic> order, {
    required String type,
    Map<String, dynamic>? table,
    Map<String, dynamic>? command,
  }) {
    return OrderPresenter.completeOfflineOrder(
      order,
      restaurantId: restaurantId,
      type: type,
      table: table,
      command: command,
    );
  }

  /// O caminho do PAGAMENTO. Pergunta só o que falta decidir.
  ///
  /// Este diálogo já foi uma revisão inteira do pedido: subtotal, taxa, total
  /// estimado e três saídas — voltar, "pagar depois" e ir para o pagamento.
  /// Mas "pagar depois" era mandar para a cozinha, escondido atrás de um botão
  /// que fala de dinheiro, e o resumo repetia número por número o que o painel
  /// do pedido mostra ao lado. O envio à produção virou botão próprio, e o que
  /// sobrou aqui são as duas escolhas da nota: taxa de serviço e CPF.
  Future<void> _finishOrder() async {
    if (activeOrder == null || orderItems.isEmpty) return;
    if (!widget.controller.session!.user.canProcessPayments) return;
    final orderId = '${activeOrder!['id']}';
    final reconciliationError = await api.reconcileOrderForPayment(orderId);
    if (!mounted) return;
    if (reconciliationError != null) {
      _error(
        ApiException(
          'Um item deste pedido precisa ser corrigido: $reconciliationError',
          statusCode: 422,
        ),
        title: 'Revise o pedido antes de pagar',
      );
      return;
    }
    await _refreshOrder();
    if (!mounted || activeOrder == null) return;

    var chargeService = activeOrder?['service_fee_enabled'] != false;
    final savedCpf = cpfDigits(activeOrder?['fiscal_customer_cpf']);
    final customerCpf = cpfDigits(selectedCustomer?['document']);
    var includeCpf = savedCpf.isNotEmpty;
    var fiscalCpf = savedCpf;
    String? cpfError;
    final cpfController = TextEditingController(
      text: formatCpf(savedCpf.isNotEmpty ? savedCpf : customerCpf),
    );
    final taxa = defaultServiceFeePercent > 0
        ? _number(activeOrder?['subtotal']) * defaultServiceFeePercent / 100
        : 0.0;

    final seguir = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AppDialog(
          title: const Text('Ir para o pagamento'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: chargeService,
                  onChanged: (value) =>
                      setDialogState(() => chargeService = value ?? true),
                  title: const Text('Cobrar taxa de serviço'),
                  subtitle: Text(
                    defaultServiceFeePercent > 0
                        ? '${defaultServiceFeePercent.toStringAsFixed(2).replaceAll('.', ',')}% · ${_money(taxa)}'
                        : 'Desmarque para retirar a taxa deste pedido.',
                  ),
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: includeCpf,
                  onChanged: (value) => setDialogState(() {
                    includeCpf = value ?? false;
                    cpfError = null;
                    if (includeCpf && cpfController.text.isEmpty) {
                      cpfController.text = formatCpf(customerCpf);
                    }
                  }),
                  title: const Text('Incluir CPF na NFC-e'),
                  subtitle: const Text(
                    'O CPF será enviado como destinatário da nota fiscal.',
                  ),
                ),
                if (includeCpf)
                  TextField(
                    key: const Key('fiscal-cpf'),
                    controller: cpfController,
                    keyboardType: TextInputType.number,
                    inputFormatters: [CpfInputFormatter()],
                    decoration: InputDecoration(
                      labelText: 'CPF para a NFC-e',
                      hintText: '000.000.000-00',
                      errorText: cpfError,
                      prefixIcon: const Icon(Icons.badge_outlined),
                    ),
                    onChanged: (_) {
                      if (cpfError != null) {
                        setDialogState(() => cpfError = null);
                      }
                    },
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Voltar'),
            ),
            FilledButton.icon(
              onPressed: () {
                if (includeCpf && !isValidCpf(cpfController.text)) {
                  setDialogState(() => cpfError = 'Informe um CPF válido.');
                  return;
                }
                fiscalCpf = includeCpf ? cpfDigits(cpfController.text) : '';
                Navigator.pop(context, true);
              },
              icon: const Icon(Icons.payments_outlined),
              label: const Text('Ir para pagamento'),
            ),
          ],
        ),
      ),
    );
    cpfController.dispose();
    if (seguir != true) return;

    final closed = await _work(() async {
      final hasPendingItems = orderItems.any(
        (item) => item['status'] == 'pending',
      );
      if (hasPendingItems) {
        await _sendPendingItemsToKitchen(
          orderItems.where((item) => item['status'] == 'pending').toList(),
        );
        await _refreshOrder();
      }
      // O fechamento (taxa de serviço, desconto, total) é aplicado pelo
      // `OrderRepository` com a MESMA conta usada aqui — `expected_total`
      // acompanha para o servidor conferir quando a operação subir.
      final closeResult = await api.post(
        '/orders/${activeOrder!['id']}/close/',
        body: {
          'discount': activeOrder?['discount'] ?? 0,
          'service_fee_enabled': chargeService,
          'fiscal_customer_cpf': fiscalCpf,
        },
        accessToken: token,
      );
      activeOrder = closeResult;
      // Online, o fechamento precisa ser confirmado antes de abrir o teclado
      // de pagamento. Offline ele permanece na fila e a venda pode continuar.
      await api.flushSalesQueue();
      final syncFailure = await api.syncFailureForOperation(
        '${closeResult['_sync_operation_id'] ?? ''}',
      );
      if (syncFailure != null) {
        throw ApiException(
          'Não foi possível fechar o pedido: $syncFailure',
          statusCode: 422,
        );
      }
      await _refreshOrder();
      return activeOrder!;
    });
    if (closed == null) return;
    // A impressão fica só para depois do pagamento (cupom fiscal) ou para o
    // fluxo automático setorizado da cozinha — não existe "nota de
    // conferência" fora desses dois: aqui só falta o caixa seguir para o
    // teclado de pagamento.
    await _paymentDialog();
  }
}
