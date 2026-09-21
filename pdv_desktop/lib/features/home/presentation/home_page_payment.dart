// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Recebimento: teclado, recebimentos montados na tela, conclusão da venda e a
/// página de pagamento.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _PaymentSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
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
  String get flowStep;
  set flowStep(String value);

  List<Map<String, dynamic>> get paymentMethods;
  set paymentMethods(List<Map<String, dynamic>> value);
  List<Map<String, dynamic>> get registeredPayments;
  set registeredPayments(List<Map<String, dynamic>> value);
  String? get selectedPaymentMethod;
  set selectedPaymentMethod(String? value);
  String get paymentDigits;
  set paymentDigits(String value);
  bool get paymentAmountTyped;
  set paymentAmountTyped(bool value);
  int get stagedPaymentSequence;
  set stagedPaymentSequence(int value);
  bool get completingOrder;
  set completingOrder(bool value);
  String? get removingPaymentId;
  set removingPaymentId(String? value);
  TextEditingController get paymentAmount;
  TextEditingController get paymentReference;

  double get paidTotal;
  double get remainingTotal;
  double get changeTotal;
  double get receivedTotal;
  double get paymentValue;
  double get pendingChange;
  Map<String, dynamic>? get selectedMethod;
  bool get selectedMethodIsCash;

  set cashSession(Map<String, dynamic>? value);
  String? get selectedRestaurantId;
  LocalDeviceAgent get deviceAgent;

  Future<void> _load();
  Future<void> _refreshOrder();
  Future<void> _emitFiscalInvoice(
    Map<String, dynamic> order, {
    bool silentIfUnconfigured,
    bool automatic,
  });
  bool _isOfflinePending(Map<String, dynamic>? value);

  Future<void> _paymentDialog() async {
    try {
      await _preparePaymentPage();
    } catch (error) {
      if (mounted) _error(error);
    }
  }

  /// Pagamentos já registrados no pedido.
  ///
  /// Offline a lista vem do cache; se nem isso existir, o pedido ainda não tem
  /// pagamento e a lista vazia é a resposta correta — não um erro.
  Future<List<Map<String, dynamic>>> _loadRegisteredPayments() async {
    try {
      final response = await api.get(
        '/orders/${activeOrder!['id']}/payments/',
        accessToken: token,
      );
      // A leitura já vem do banco local e traz tanto os recebimentos
      // confirmados quanto os que ainda estão na fila (§3).
      return ((response['results'] ?? response['data'] ?? <dynamic>[]) as List)
          .cast<Map<String, dynamic>>();
    } on ApiException catch (error) {
      if (!error.isConnectivity) rethrow;
      return (activeOrder?['offline_payments'] as List? ?? registeredPayments)
          .whereType<Map>()
          .map((value) => Map<String, dynamic>.from(value))
          .toList();
    }
  }

  Future<void> _preparePaymentPage() async {
    // O teclado nasce preenchido com o restante, então o total precisa ser o
    // que o servidor tem agora — não uma cópia anterior à retirada da taxa de
    // serviço, que faria o caixa cobrar o valor cheio sem perceber. Uma falha
    // aqui não pode impedir o recebimento: seguimos com o que já está em mão.
    //
    // As três leituras são independentes entre si — o pedido, o catálogo de
    // formas de pagamento e os recebimentos já lançados. Encadeá-las somava
    // três idas ao armazenamento (e, no primeiro acesso de cada uma, três
    // idas à rede) antes de a tela aparecer. O identificador do pedido não
    // muda no meio, então lê-las juntas é seguro.
    final resultados = await Future.wait([
      _refreshOrder().then<Object?>((_) => null).catchError((Object _) => null),
      _list('/payments/methods/', query: {
        'restaurant': restaurantId,
        'is_active': true,
        'page_size': 100,
      }),
      // Sem rede e sem cópia guardada, o pedido simplesmente ainda não tem
      // pagamentos — tratar isso como falha impediria de receber offline, que
      // é exatamente quando o operador mais precisa concluir a venda.
      _loadRegisteredPayments(),
    ]);
    paymentMethods = resultados[1] as List<Map<String, dynamic>>;
    registeredPayments = resultados[2] as List<Map<String, dynamic>>;
    selectedPaymentMethod = paymentMethods.isEmpty
        ? null
        : '${paymentMethods.first['id']}';
    paymentAmountTyped = false;
    paymentDigits = (remainingTotal * 100).round().toString();
    _syncPaymentAmount();
    paymentReference.clear();
    setState(() => flowStep = 'payment');
  }

  void _pressPaymentKey(String key) {
    setState(() {
      paymentAmountTyped = true;
      if (key == 'clear') {
        paymentDigits = '0';
      } else if (key == 'back') {
        paymentDigits = paymentDigits.length <= 1
            ? '0'
            : paymentDigits.substring(0, paymentDigits.length - 1);
      } else {
        paymentDigits = paymentDigits == '0' ? key : '$paymentDigits$key';
        if (paymentDigits.length > 9) {
          paymentDigits = paymentDigits.substring(0, 9);
        }
      }
      _syncPaymentAmount();
    });
  }

  /// O MESMO valor, agora digitado no campo em vez de clicado no teclado.
  ///
  /// O campo era só um visor: `readOnly`, alimentado pelas teclas da tela. Num
  /// caixa com teclado físico isso obriga a soltar as mãos e ir ao mouse para
  /// um número que já está debaixo dos dedos.
  ///
  /// A regra de leitura é a MESMA das teclas — os dígitos entram pela direita,
  /// os dois últimos são os centavos. Ler o texto como um decimal comum daria
  /// ao campo um comportamento e ao teclado outro, e "12" significaria R$ 0,12
  /// ou R$ 12,00 dependendo de como o operador tivesse entrado com o valor.
  void _typePaymentAmount(String raw) {
    setState(() {
      paymentAmountTyped = true;
      paymentDigits = OrderPresenter.typedPaymentDigits(raw);
      _syncPaymentAmount();
    });
  }

  /// Reapresenta o restante no teclado enquanto ninguém digitou nada.
  ///
  /// O valor era fixado UMA vez, ao abrir a tela, e não acompanhava mais nada.
  /// Só que o total do pedido ainda muda depois disso: a taxa de serviço
  /// aplicada no fechamento chega pela sincronização, um recebimento sai da
  /// lista, o servidor devolve um total diferente do calculado aqui. O resumo
  /// à esquerda se atualizava e o teclado ficava para trás — o operador via
  /// "Restante R$ 12,43" e o teclado oferecendo R$ 11,00, que é o subtotal sem
  /// a taxa. Cobrar a menos é um erro que só aparece no fechamento do caixa.
  void _refreshSuggestedPaymentAmount() {
    if (paymentAmountTyped) return;
    final suggested = (remainingTotal * 100).round().toString();
    if (suggested == paymentDigits) return;
    paymentDigits = suggested;
    _syncPaymentAmount();
  }

  void _syncPaymentAmount() {
    paymentAmount.text = paymentValue.toStringAsFixed(2).replaceAll('.', ',');
    paymentAmount.selection = TextSelection.collapsed(
      offset: paymentAmount.text.length,
    );
  }

  /// Débito/crédito não é escolhido à parte: o próprio método de pagamento
  /// selecionado já diz qual é ("Cartão de Débito", "Cartão de Crédito"),
  /// como cadastrado em Formas de pagamento. Isso só preenche o metadado
  /// que o backend persiste no pagamento e envia como meio correto na NFC-e.
  String _cardSubtypeFor(Map<String, dynamic> method) {
    final name = '${method['name']}'.toLowerCase();
    if (name.contains('débito') || name.contains('debito')) return 'debit';
    return 'credit';
  }

  /// Monta o recebimento NA TELA. Nada sai daqui para o servidor.
  ///
  /// O envio acontece no clique de **Concluir pedido**, com todos juntos.
  /// Antes, cada forma de pagamento adicionada já era um `POST /pay/`: o
  /// pedido virava "pago" no instante em que o operador escolhia o método —
  /// antes de conferir troco, referência ou de decidir dividir a conta — e
  /// desfazer virava problema do servidor. Com a operação já na fila, excluir
  /// devolvia HTTP 409 ("este recebimento já está subindo"), e o caixa ficava
  /// com um recebimento que não conseguia tirar.
  ///
  /// Encenar aqui também é o que faz recibo e DANFE saírem no mesmo gesto: a
  /// venda passa a paga e o papel sai em seguida, sem uma janela entre as duas
  /// coisas em que o operador pudesse sair da tela.
  void _addSplitPayment() {
    if (selectedPaymentMethod == null || paymentValue <= 0) return;
    final method = paymentMethods.firstWhere(
      (item) => '${item['id']}' == selectedPaymentMethod,
    );
    final isCash = method['method_type'] == 'cash';
    // Qualquer forma pode receber acima do restante e devolver troco. A
    // restrição a dinheiro travava o caixa em situações reais — a maquininha
    // cobrou um valor redondo, o cliente pediu parte em espécie de volta — e
    // a única saída era refazer a venda inteira.
    stagedPaymentSequence += 1;
    final staged = <String, dynamic>{
      // Id local: é o que dá o botão de excluir à linha. Ele nunca vai ao
      // servidor — o corpo enviado depois é o `_staged_body`.
      ...OrderPresenter.stagedPayment(
        localId: 'staged-$stagedPaymentSequence',
        method: method,
        received: paymentValue,
        remaining: remainingTotal,
      ),
      '_staged_body': <String, dynamic>{
        'payment_method': selectedPaymentMethod,
        'amount': paymentValue.toStringAsFixed(2),
        // A gaveta entra na conta sempre que o dinheiro passa por ela: um
        // recebimento em espécie, ou o TROCO de qualquer forma — ele sai em
        // espécie mesmo quando o pagamento foi no cartão.
        if (cashSession?['id'] != null &&
            (isCash || paymentValue > remainingTotal + .009))
          'cash_register': cashSession!['id'],
        // A chave é gerada AGORA e viaja com a operação: um reenvio depois de
        // um erro de rede é reconhecido como repetição, não como um segundo
        // recebimento.
        'idempotency_key':
            'flutter-${activeOrder!['id']}-${DateTime.now().microsecondsSinceEpoch}',
        'metadata': {
          'card_subtype': method['method_type'] == 'card'
              ? _cardSubtypeFor(method)
              : '',
          'reference': paymentReference.text.trim(),
          'source': 'flutter_pdv',
        },
      },
    };
    setState(() {
      registeredPayments = [...registeredPayments, staged];
      paymentAmountTyped = false;
      paymentDigits = (remainingTotal * 100).round().toString();
      _syncPaymentAmount();
      paymentReference.clear();
    });
  }

  /// Recebimentos que ainda não foram enviados ao servidor.
  List<Map<String, dynamic>> get stagedPayments => registeredPayments
      .where((payment) => payment['_staged'] == true)
      .toList(growable: false);

  /// Envia, em ordem, os recebimentos encenados na tela.
  ///
  /// Devolve `false` quando algum não subiu. O que já subiu continua valendo
  /// (o servidor é a verdade) e o que faltou permanece na tela para o operador
  /// decidir. Parar no primeiro erro é deliberado: insistir nos seguintes só
  /// empilharia recusas do mesmo motivo.
  Future<bool> _commitStagedPayments() async {
    final staged = stagedPayments;
    if (staged.isEmpty) return true;
    final pending = <Map<String, dynamic>>[];
    var touchedCash = false;
    var stop = false;
    for (final payment in staged) {
      if (stop) {
        pending.add(payment);
        continue;
      }
      final result = await _work(
        () => api.post(
          '/orders/${activeOrder!['id']}/pay/',
          body: payment['_staged_body'] as Map<String, dynamic>,
          accessToken: token,
        ),
      );
      if (result == null) {
        pending.add(payment);
        stop = true;
        continue;
      }
      touchedCash = touchedCash || _isCashPayment(payment);
    }
    // Cada `pay` só retorna depois que o servidor confirmou, então quando se
    // chega aqui o pedido já está quitado LÁ. É o que a emissão fiscal exige:
    // uma nota emitida antes dos recebimentos sairia com o DANFE sem as
    // formas de pagamento — justamente o que o cliente confere.
    await _refreshOrder();
    final confirmed = await _loadRegisteredPayments();
    registeredPayments = [...confirmed, ...pending];
    if (touchedCash) await _refreshCashSession();
    if (mounted) setState(() {});
    return pending.isEmpty;
  }

  /// O recebimento saiu da gaveta?
  ///
  /// O lançamento criado aqui guarda `method_type`; o que vem do servidor usa
  /// `payment_method_type` (ver `PaymentSerializer`). A mesma lista mistura os
  /// dois, e olhar só um dos nomes deixava o saldo do caixa parado depois de
  /// remover um recebimento já sincronizado.
  static bool _isCashPayment(Map<String, dynamic> payment) =>
      '${payment['method_type'] ?? payment['payment_method_type'] ?? ''}' ==
      'cash';

  /// Relê o saldo da gaveta depois de mexer em dinheiro.
  Future<void> _refreshCashSession() async {
    try {
      cashSession = await api.get(
        '/cash-register/current/',
        query: {
          if (selectedRestaurantId != null) 'restaurant': selectedRestaurantId,
        },
        accessToken: token,
      );
    } on ApiException {
      // O recebimento já foi registrado; a atualização geral tenta de novo.
    }
  }

  /// Remove um pagamento do pedido, como no frontend web.
  ///
  /// O recebimento ENCENADO (ainda só na tela) some daqui mesmo; o que já foi
  /// enviado é cancelado pelo servidor, que é quem sabe reabrir mesa, comanda
  /// e estorno de estoque.
  Future<void> _removePayment(Map<String, dynamic> payment) async {
    final id = payment['id'];
    if (id == null || removingPaymentId != null) return;
    // Encenado: some da tela e pronto. Não existe em lugar nenhum além daqui,
    // então não há o que o servidor desfazer — e era justamente por pedir isso
    // a ele que excluir devolvia 409 antes de a venda sequer ter subido.
    if (payment['_staged'] == true) {
      setState(() {
        registeredPayments = registeredPayments
            .where((item) => !identical(item, payment))
            .toList();
        paymentAmountTyped = false;
        paymentDigits = (remainingTotal * 100).round().toString();
        _syncPaymentAmount();
      });
      return;
    }
    setState(() => removingPaymentId = '$id');
    try {
      await api.delete(
        '/orders/${activeOrder!['id']}/payments/$id/',
        accessToken: token,
      );
      await _refreshOrder();
      registeredPayments = await _loadRegisteredPayments();
      if (_isCashPayment(payment)) await _refreshCashSession();
      paymentDigits = (remainingTotal * 100).round().toString();
      _syncPaymentAmount();
    } catch (error) {
      if (mounted) {
        _error(error, title: 'Não foi possível excluir o pagamento');
      }
    } finally {
      if (mounted) setState(() => removingPaymentId = null);
    }
  }

  Future<void> _completePaidOrder() async {
    if (completingOrder) return;
    if (remainingTotal > .009) {
      _error(const ApiException('Ainda existe um valor restante para pagar.'));
      return;
    }
    completingOrder = true;
    try {
      await _completePaidOrderNow();
    } finally {
      if (mounted) setState(() => completingOrder = false);
    }
  }

  Future<void> _completePaidOrderNow() async {
    // Os recebimentos sobem AGORA, todos juntos, e só então a venda vira paga.
    // É o que mantém recibo e DANFE no mesmo gesto: sem isto, o pedido já
    // estava pago desde que o operador escolheu a forma de pagamento, e o
    // papel dependia de ele lembrar de voltar aqui.
    if (!await _commitStagedPayments()) return;
    if (!mounted) return;
    if (remainingTotal > .009) {
      // O servidor cobrou diferente do que a tela somava (preço mudou, taxa
      // entrou). Melhor parar aqui do que concluir uma venda em aberto.
      _error(
        const ApiException(
          'O servidor registrou um valor diferente do somado na tela. '
          'Confira os recebimentos antes de concluir.',
        ),
      );
      return;
    }
    // O recibo é um efeito colateral: uma falha de impressão não pode reabrir
    // uma venda concluída.
    await _printSaleReceipt();
    if (!mounted) return;
    // A VENDA ESTÁ CONCLUÍDA AQUI. A NFC-e é consequência dela, não condição.
    //
    // Esperar a emissão para liberar a tela transformava cada problema fiscal
    // — perfil sem NCM, provedor fora do ar, limite de requisições do servidor
    // — em uma venda que não fecha, com o cliente parado no balcão. O
    // documento é pedido ao servidor no gesto, mas quem espera pela
    // autorização da SEFAZ e pelo cupom é uma espera em segundo plano, não o
    // operador.
    final orderForInvoice = activeOrder!;
    setState(() {
      activeOrder = null;
      selectedTable = null;
      selectedCommand = null;
      selectedCustomer = null;
      orderItems = [];
      registeredPayments = [];
      // A venda acabou: a tela volta PRONTA para a próxima, no catálogo com
      // o carrinho vazio. Voltar para um seletor de tipo custaria um gesto a
      // cada cliente da fila.
      orderType = 'counter';
      flowStep = 'order';
    });
    unawaited(_load());
    unawaited(
      _emitFiscalInvoice(
        orderForInvoice,
        silentIfUnconfigured: true,
        automatic: true,
      ),
    );
  }

  /// Imprime o recibo da venda no gesto de concluir o pedido.
  ///
  /// O cupom vem do servidor (`/orders/{id}/print/`), que é quem sabe o preço,
  /// o imposto e o layout; este terminal escolhe a impressora e põe no papel.
  /// `manual_only` tira o trabalho do laço automático do agente — quem
  /// imprime é este gesto, e uma falha aqui precisa aparecer na tela em vez de
  /// virar um cupom que ninguém sabe que existe.
  Future<void> _printSaleReceipt() async {
    try {
      final printers = await _list(
        '/printers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      );
      if (!mounted) return;
      if (printers.isEmpty) {
        _error(
          const ApiException(
            'Nenhuma impressora ativa foi cadastrada para este restaurante.',
          ),
          title: 'O pagamento foi registrado, mas o recibo não saiu',
        );
        return;
      }
      final master = widget.preferences.masterPrinterId;
      final hasMaster = printers.any((p) => '${p['id']}' == master);
      final printerId = hasMaster
          ? master
          : await showDialog<String>(
              context: context,
              builder: (_) => PrinterSelectionDialog(
                printers: printers,
                title: 'Imprimir recibo de venda',
                summary:
                    'Pedido #${activeOrder?['sequence']} · ${_money(activeOrder?['total'])}',
                description:
                    'O recibo contém itens, pagamentos e totais do pedido.',
              ),
            );
      if (printerId == null || !mounted) return;
      final chosen = printers.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == printerId,
        orElse: () => null,
      );
      final printJob = await api.post(
        '/orders/${activeOrder!['id']}/print/',
        body: {
          'job_type': 'receipt',
          'printer': printerId,
          'manual_only': true,
        },
        accessToken: token,
      );
      final printer = printJob['printer'] as Map<String, dynamic>? ?? chosen;
      if (printer == null) {
        throw const ApiException(
          'O trabalho de impressão voltou sem impressora.',
        );
      }
      await deviceAgent.printJobManually(printJob, printer);
    } catch (error) {
      if (mounted) {
        _error(
          error,
          title: 'O pagamento foi registrado, mas o recibo não saiu',
          action: 'Reimprima pela tela de Pedidos quando quiser.',
        );
      }
    }
  }
}
