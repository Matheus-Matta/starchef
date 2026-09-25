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
  Future<void> _load();
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

  /// Persiste o pedido somente quando o primeiro produto vai ser incluído.
  /// Escolher tipo, cliente, mesa ou comanda prepara o contexto sem deixar
  /// pedidos vazios abandonados no servidor.
  Future<void> _ensureOrderStarted() async {
    if (activeOrder != null) return;
    final type = orderType;
    if (type == null) {
      throw const ApiException('Escolha o tipo de atendimento.');
    }
    if (selectedCommand != null) {
      activeOrder = await api.post(
        '/orders/open-command/',
        body: {'command': selectedCommand!['id']},
        accessToken: token,
      );
    } else {
      activeOrder = await api.post(
        '/orders/',
        body: {
          'restaurant': restaurantId,
          'order_type': type,
          if (selectedCustomer != null) 'customer': selectedCustomer!['id'],
        },
        accessToken: token,
      );
    }
    activeOrder = _completeOfflineOrder(
      activeOrder!,
      type: type,
      table: selectedTable,
      command: selectedCommand,
    );
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
    if (!widget.controller.session!.user.canProcessPayments) return;
    // O outro gesto que faz o pedido nascer: o caixa vai anexar um
    // recebimento, e recebimento se anexa a pedido. A permissão é conferida
    // ANTES de materializar — abrir um pedido para em seguida recusar o
    // pagamento deixaria para trás exatamente o lixo que adiar evita.
    if (_draftIsLive && !await _materializeDraft()) return;
    if (activeOrder == null || orderItems.isEmpty) return;
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
        savedCoupon: '${activeOrder?['coupon_code'] ?? ''}',
        couponDiscount: _number(activeOrder?['coupon_discount']),
      ),
    );
    final seguir = escolha != null;
    final chargeService = escolha?.chargeService ?? true;
    final fiscalCpf = escolha?.fiscalCpf ?? '';
    final couponCode = escolha?.couponCode ?? '';
    if (!seguir) return;

    // O TITULO CITA O CUPOM porque ele e a causa mais provavel de o fechamento
    // ser recusado com o corpo todo certo: o servidor devolve 422
    // (`coupon_rejected`) com o motivo em portugues, e sem o titulo o caixa le
    // "CPF ja usou este cupom" sob um cabecalho generico de falha e conclui que
    // o problema e o CPF.
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
          // Sempre presente, inclusive vazio: vazio RETIRA o cupom. Omitir
          // significaria "nao mexe", e o caixa que apagou o codigo de proposito
          // — porque o cliente desistiu dele — veria o desconto continuar.
          'coupon_code': couponCode,
        },
        accessToken: token,
      );
      // O fechamento já foi confirmado pelo servidor: `api.patch` só retorna
      // depois que ele respondeu. O teclado de pagamento abre sobre um pedido
      // que existe fechado do outro lado.
      activeOrder = closeResult;
      await _refreshOrder();
      return activeOrder!;
    }, errorTitle: 'Não foi possível fechar o pedido');
    if (closed == null) return;
    // A impressão fica só para depois do pagamento (cupom fiscal) ou para o
    // fluxo automático setorizado da cozinha — não existe "nota de
    // conferência" fora desses dois: aqui só falta o caixa seguir para o
    // teclado de pagamento.
    await _paymentDialog();
  }
}

/// O que o operador decidiu no diálogo de "ir para o pagamento".
