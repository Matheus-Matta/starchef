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
  bool get abrindoPagamento;
  set abrindoPagamento(bool value);
  void _leaveActiveOrder({String? except});
  Future<void> _load();
  Future<String?> _autorizarDesconto(String motivo);
  Future<void> _ajustarFechamento(
    Map<String, dynamic> mudanca, {
    String? senha,
  });
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
    // A prévia da tela de pagamento ainda não existe no servidor.
    if (!draft.pedidoExisteNoServidor(activeOrder)) return;
    _aplicarPedido(
      await api.get('/orders/${activeOrder!['id']}/', accessToken: token),
    );
  }

  /// Põe na tela o pedido que ACABOU de chegar do servidor.
  ///
  /// Quem já tem o pedido em mãos (o detalhe recém-lido, a resposta do
  /// `/close/`) usa isto em vez de `_refreshOrder`: os dois faziam o mesmo GET
  /// em seguida, e abrir uma mesa ou comanda custava duas idas ao servidor.
  void _aplicarPedido(Map<String, dynamic> pedido) {
    activeOrder = pedido;
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

  /// O caminho do PAGAMENTO: leva direto à tela de pagamento.
  ///
  /// Aqui já houve um diálogo — primeiro uma revisão inteira do pedido, depois
  /// só as escolhas da nota (taxa de serviço, CPF/CNPJ e cupom). Ele saiu: as
  /// três ficam na própria tela de pagamento (`_PaymentAdjustSection` e
  /// `_PaymentCouponSection`), onde o caixa decide vendo o total, e muda
  /// depois sem voltar.
  /// "Ir para pagamento", com o botão avisando enquanto abre.
  Future<void> _finishOrder() async {
    if (abrindoPagamento) return; // duplo clique, ou Enter segurado
    setState(() => abrindoPagamento = true);
    try {
      await _abrirPagamento();
    } finally {
      if (mounted) setState(() => abrindoPagamento = false);
    }
  }

  Future<void> _abrirPagamento() async {
    if (!widget.controller.session!.user.canProcessPayments) return;
    // O outro gesto que faz o pedido nascer: o caixa vai anexar um
    // recebimento, e recebimento se anexa a pedido. A permissão é conferida
    // ANTES de materializar — abrir um pedido para em seguida recusar o
    // pagamento deixaria para trás exatamente o lixo que adiar evita.
    //
    // Com rascunho, o pedido NÃO nasce aqui: o servidor calcula o total sem
    // gravar (`simular`), e o pedido nasce na conclusão, junto com os
    // recebimentos — um envio só, em vez de criar, lançar item a item, fechar
    // e pagar em chamadas separadas que uma troca loja/nuvem partia ao meio.
    var simulando = _draftIsLive;
    // O fechamento vai na PRIMEIRA simulação (`fechamento_inicial.dart`):
    // eram duas idas ao servidor antes de a tela de pagamento abrir.
    if (simulando) draft.fechamento = fechamentoInicial();
    // Balcão: a tela abre NA HORA e o servidor confirma em paralelo
    // (`previa_local.dart`); com comanda, espera a resposta como antes.
    final naHora = simulando && podeAbrirNaHora(draft);
    if (naHora) {
      _abrirPreviaLocal();
    } else if (simulando && !await _simularVenda()) {
      draft.fechamento = null;
      // A recusa abriu a conta onde a comanda já estava: se ela está em
      // aberto, o caixa segue para pagá-la; paga, fica só aberta na tela.
      final aberta =
          activeOrder != null &&
          !draft.simulada &&
          activeOrder?['payment_status'] != 'paid';
      if (!aberta) return;
      simulando = false;
    }
    if (!simulando) {
      await _refreshOrder();
    }
    if (!mounted || activeOrder == null || orderItems.isEmpty) return;

    // SEM MODAL. Taxa, CPF/CNPJ e desconto ficam na TELA DE PAGAMENTO
    // (`_PaymentAdjustSection`), onde o caixa vê o total enquanto decide —
    // antes eram escolhidos aqui, num diálogo, sem ver o número. Entram os
    // valores de partida que o diálogo já trazia marcados: a taxa do pedido,
    // o documento já gravado nele e o cupom que ele tinha.
    final chargeService = activeOrder?['service_fee_enabled'] != false;
    final fiscalCpf = cpfDigits(activeOrder?['fiscal_customer_cpf']);
    final fiscalCnpj = cnpjDigits(activeOrder?['fiscal_customer_cnpj']);
    final couponCode = '${activeOrder?['coupon_code'] ?? ''}'.trim();
    if (simulando) {
      // Taxa, CPF e cupom vão no envio da conclusão: os da prévia, que o
      // servidor já calculou com o padrão do pedido — sem simular de novo.
      draft.fechamento = {
        'discount': activeOrder?['discount'] ?? 0,
        'service_fee_enabled': chargeService,
        'fiscal_customer_cpf': fiscalCpf,
        'fiscal_customer_cnpj': fiscalCnpj,
        'coupon_code': couponCode,
      };
      await _paymentDialog();
      return;
    }

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
      // O desconto que o pedido já tinha: o desconto se decide na TELA DE
      // PAGAMENTO (`_PaymentAdjustSection`), que pede a aprovação quando
      // precisa. Fechar de novo com o mesmo valor não pede senha.
      final closeResult = await api.post(
        '/orders/${activeOrder!['id']}/close/',
        body: {
          'discount': activeOrder?['discount'] ?? 0,
          'service_fee_enabled': chargeService,
          'fiscal_customer_cpf': fiscalCpf,
          'fiscal_customer_cnpj': fiscalCnpj,
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
      // A resposta do `/close/` é o pedido inteiro (o mesmo serializer do
      // GET): reler logo em seguida só repetia a ida ao servidor.
      _aplicarPedido(closeResult);
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
