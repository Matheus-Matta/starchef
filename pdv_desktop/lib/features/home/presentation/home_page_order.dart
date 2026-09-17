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
  void _leaveActiveOrder({String? except});
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;

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

  void _refreshSuggestedPaymentAmount();
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
    _leaveActiveOrder();
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

  /// Relê o pedido no servidor.
  ///
  /// É a única fonte: total, taxa de serviço e desconto são calculados lá, e
  /// um item pode ter sido lançado em outro caixa desde a última leitura.
  Future<void> _refreshOrder() async {
    if (activeOrder == null) return;
    activeOrder = await api.get(
      '/orders/${activeOrder!['id']}/',
      accessToken: token,
    );
    final items = activeOrder!['items'] as List? ?? [];
    orderItems = items
        .cast<Map<String, dynamic>>()
        .where((item) => item['status'] != OrderItemStatus.legacyVoided)
        .toList();
    // O total pode ter mudado aqui: quem calcula taxa de serviço e desconto
    // é o servidor, e é nesta leitura que o número dele chega à tela.
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
    await _refreshOrder();
    if (!mounted || activeOrder == null) return;

    final taxa = defaultServiceFeePercent > 0
        ? _number(activeOrder?['subtotal']) * defaultServiceFeePercent / 100
        : 0.0;

    // O diálogo é dono do controlador de CPF e o descarta no `dispose` do seu
    // `State` — que só roda depois que a rota termina de sair. Criá-lo aqui e
    // descartá-lo logo após o `await` descarta cedo demais: o `await showDialog`
    // volta com a animação de saída ainda rodando.
    final escolha = await showDialog<_FinishOrderChoice>(
      context: context,
      builder: (_) => _FinishOrderForm(
        chargeService: activeOrder?['service_fee_enabled'] != false,
        savedCpf: cpfDigits(activeOrder?['fiscal_customer_cpf']),
        customerCpf: cpfDigits(selectedCustomer?['document']),
        serviceFeePercent: defaultServiceFeePercent,
        serviceFeeAmount: taxa,
        money: _money,
      ),
    );
    final seguir = escolha != null;
    final chargeService = escolha?.chargeService ?? true;
    final fiscalCpf = escolha?.fiscalCpf ?? '';
    if (!seguir) return;

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
      // O fechamento já foi confirmado pelo servidor: `api.patch` só retorna
      // depois que ele respondeu. O teclado de pagamento abre sobre um pedido
      // que existe fechado do outro lado.
      activeOrder = closeResult;
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


/// O que o operador decidiu no diálogo de "ir para o pagamento".
class _FinishOrderChoice {
  const _FinishOrderChoice({
    required this.chargeService,
    required this.fiscalCpf,
  });

  final bool chargeService;

  /// Só dígitos, ou vazio quando o CPF não vai na nota.
  final String fiscalCpf;
}

/// As duas escolhas da nota: taxa de serviço e CPF.
///
/// É um widget com estado porque ele é DONO do `TextEditingController` — ver
/// `_MovementApprovalForm` para o defeito que isso evita.
class _FinishOrderForm extends StatefulWidget {
  const _FinishOrderForm({
    required this.chargeService,
    required this.savedCpf,
    required this.customerCpf,
    required this.serviceFeePercent,
    required this.serviceFeeAmount,
    required this.money,
  });

  final bool chargeService;
  final String savedCpf;
  final String customerCpf;
  final double serviceFeePercent;
  final double serviceFeeAmount;
  final String Function(dynamic value) money;

  @override
  State<_FinishOrderForm> createState() => _FinishOrderFormState();
}

class _FinishOrderFormState extends State<_FinishOrderForm> {
  late var _chargeService = widget.chargeService;
  late var _includeCpf = widget.savedCpf.isNotEmpty;
  late final _cpf = TextEditingController(
    text: formatCpf(
      widget.savedCpf.isNotEmpty ? widget.savedCpf : widget.customerCpf,
    ),
  );
  String? _cpfError;

  @override
  void dispose() {
    _cpf.dispose();
    super.dispose();
  }

  void _confirm() {
    if (_includeCpf && !isValidCpf(_cpf.text)) {
      setState(() => _cpfError = 'Informe um CPF válido.');
      return;
    }
    Navigator.pop(
      context,
      _FinishOrderChoice(
        chargeService: _chargeService,
        fiscalCpf: _includeCpf ? cpfDigits(_cpf.text) : '',
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AppDialog(
    title: const Text('Ir para o pagamento'),
    content: SizedBox(
      width: 420,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: _chargeService,
            onChanged: (value) =>
                setState(() => _chargeService = value ?? true),
            title: const Text('Cobrar taxa de serviço'),
            subtitle: Text(
              widget.serviceFeePercent > 0
                  ? '${widget.serviceFeePercent.toStringAsFixed(2).replaceAll('.', ',')}'
                        ' · ${widget.money(widget.serviceFeeAmount)}'
                  : 'Desmarque para retirar a taxa deste pedido.',
            ),
          ),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: _includeCpf,
            onChanged: (value) => setState(() {
              _includeCpf = value ?? false;
              _cpfError = null;
              if (_includeCpf && _cpf.text.isEmpty) {
                _cpf.text = formatCpf(widget.customerCpf);
              }
            }),
            title: const Text('Incluir CPF na NFC-e'),
            subtitle: const Text(
              'O CPF será enviado como destinatário da nota fiscal.',
            ),
          ),
          if (_includeCpf)
            TextField(
              key: const Key('fiscal-cpf'),
              controller: _cpf,
              keyboardType: TextInputType.number,
              inputFormatters: [CpfInputFormatter()],
              decoration: InputDecoration(
                labelText: 'CPF para a NFC-e',
                hintText: '000.000.000-00',
                errorText: _cpfError,
                prefixIcon: const Icon(Icons.badge_outlined),
              ),
              onChanged: (_) {
                if (_cpfError != null) setState(() => _cpfError = null);
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
        onPressed: _confirm,
        icon: const Icon(Icons.payments_outlined),
        label: const Text('Ir para pagamento'),
      ),
    ],
  );
}
