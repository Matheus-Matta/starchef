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
  set couponBusy(bool value);
  set adjustBusy(bool value);
  CalculoDoTotal get calculoDoTotal;
  bool get _calculandoTotal;
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
  Map<String, dynamic>? get selectedRestaurant;
  LocalDeviceAgent get deviceAgent;

  Future<void> _refreshOrder();
  Future<bool> _aplicarDocumentoPendente();
  void _seguirDepoisDePago();
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
    // Venda simulada: o pedido ainda não existe no servidor — não há o que
    // recarregar nem recebimento gravado; só as formas de pagamento.
    final simulada = draft.simulada;
    // As formas já vieram com o catálogo na abertura do PDV. Na venda nova a
    // tela abre COM elas e a lista é relida em segundo plano: esperar essa
    // leitura era de 0,5 a 4 s na nuvem com a tela parada (pdv.log).
    final jaTemFormas = simulada && paymentMethods.isNotEmpty;
    if (jaTemFormas) unawaited(_atualizarFormasDePagamento());
    final resultados = await Future.wait([
      simulada
          ? Future<Object?>.value()
          : _refreshOrder()
                .then<Object?>((_) => null)
                .catchError((Object _) => null),
      jaTemFormas
          ? Future.value(paymentMethods)
          : _list('/payments/methods/', query: _consultaDasFormas),
      // Sem rede e sem cópia guardada, o pedido simplesmente ainda não tem
      // pagamentos — tratar isso como falha impediria de receber offline, que
      // é exatamente quando o operador mais precisa concluir a venda.
      simulada
          ? Future.value(<Map<String, dynamic>>[])
          : _loadRegisteredPayments(),
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
    // Um ajuste ainda no ar de uma visita anterior não vale para esta.
    calculoDoTotal.descartar();
    // O Esc desta visita só desfaz o que for feito NELA.
    draft.desfazer.esquecer('payment');
    couponBusy = false;
    adjustBusy = false;
    setState(() => flowStep = 'payment');
  }

  /// A MESMA consulta do catálogo (`pdv_catalog.dart`): uma entrada de cache
  /// serve às duas, e a mais usada vem primeiro e já selecionada.
  Map<String, dynamic> get _consultaDasFormas => {
    'restaurant': restaurantId,
    'is_active': true,
    'page_size': 100,
    'ordering': '-uso,name',
  };

  /// Relê as formas sem segurar a tela; a escolhida continua escolhida.
  Future<void> _atualizarFormasDePagamento() async {
    try {
      final formas = await _list(
        '/payments/methods/',
        query: _consultaDasFormas,
      );
      if (!mounted || formas.isEmpty) return;
      setState(() {
        paymentMethods = formas;
        final aindaExiste = formas.any(
          (forma) => '${forma['id']}' == selectedPaymentMethod,
        );
        if (!aindaExiste) selectedPaymentMethod = '${formas.first['id']}';
      });
    } catch (_) {
      // Fica a lista que já estava na tela: é a mesma do catálogo.
    }
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

  /// O total MUDOU (desconto, taxa, cupom): o valor sugerido volta a ser o
  /// restante novo. O que o caixa tinha digitado era para o total antigo, e
  /// mantê-lo deixava a coluna das formas de pagamento com o valor de antes
  /// do desconto.
  void _valorSugeridoDoNovoTotal() {
    paymentAmountTyped = false;
    _refreshSuggestedPaymentAmount();
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
  Future<void> _addSplitPayment() async {
    // A mesma trava do botão, para o Enter e o atalho: sobre um total que
    // ainda está sendo calculado, nada se registra.
    if (_calculandoTotal) return;
    if (selectedPaymentMethod == null || paymentValue <= 0) return;
    // CPF/CNPJ digitado sem o ✓ entra na nota agora; inválido trava aqui.
    if (!await _aplicarDocumentoPendente() || !mounted) return;
    if (_calculandoTotal || selectedPaymentMethod == null) return;
    if (paymentValue <= 0) return;
    final method = paymentMethods.firstWhere(
      (item) => '${item['id']}' == selectedPaymentMethod,
    );
    final isCash = method['method_type'] == 'cash';
    // Qualquer forma dá troco, a não ser que o restaurante só o queira em
    // dinheiro (`troco_so_em_dinheiro.dart`).
    final recusa = recusaDoTroco(
      restaurante: selectedRestaurant,
      forma: method,
      recebido: paymentValue,
      restante: remainingTotal,
    );
    if (recusa != null) return _error(ApiException(recusa));
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
        // A IDENTIDADE do recebimento, dada aqui. Loja e nuvem aceitam receber
        // (o terminal escolhe, e desvia quando um cai): enviado aos dois, o
        // mesmo UUID vira UMA linha quando a sincronização os junta, e um
        // envio atrasado com horário mais velho não sobrescreve nada
        // (`payments/recebimento_por_uuid.py`).
        'id': LocalId.uuid(),
        'client_updated_at': DateTime.now().toUtc().toIso8601String(),
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
    // Esc tira ESTE recebimento (o mais recente primeiro), e não todos.
    draft.desfazer.empilhar(
      'payment',
      '${method['name'] ?? 'Pagamento'}',
      () => _tirarRecebimentoMontado(staged),
    );
  }

  /// Tira da tela um recebimento ainda não enviado (o Esc e a lixeira).
  void _tirarRecebimentoMontado(Map<String, dynamic> payment) {
    if (!registeredPayments.any((item) => identical(item, payment))) return;
    setState(() {
      registeredPayments = registeredPayments
          .where((item) => !identical(item, payment))
          .toList();
      paymentAmountTyped = false;
      paymentDigits = (remainingTotal * 100).round().toString();
      _syncPaymentAmount();
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
    if (staged.isEmpty && !draft.simulada) return true;
    final corpos = [
      for (final pagamento in staged)
        Map<String, dynamic>.from(pagamento['_staged_body'] as Map),
    ];
    final touchedCash = staged.any(_isCashPayment);
    if (draft.simulada) {
      // A venda inteira num envio: pedido, cozinha, fechamento e recebimentos.
      if (!await _concluirVendaSimulada(corpos)) return false;
    } else {
      // Pedido que já existia (Ctrl + E antes): os recebimentos num envio só, não
      // um por chamada — tudo ou nada, com o UUID de cada um.
      final feito = await _workResolvendo(
        () => OrderDraftMaterializer(api, accessToken: token).receber(
          orderId: '${activeOrder!['id']}',
          restaurantId: restaurantId,
          recebimentos: corpos,
        ),
        errorTitle: 'Não foi possível registrar os recebimentos',
        fica: true,
      );
      if (feito == null) return false;
      // Pedido e recebimentos ao mesmo tempo: uma ida a menos no "Concluir".
      final lidos = await Future.wait([
        _refreshOrder().then<Object?>((_) => null),
        _loadRegisteredPayments(),
      ]);
      registeredPayments = lidos[1]! as List<Map<String, dynamic>>;
    }
    // O saldo da gaveta é só exibição: relido em segundo plano, não segura a
    // próxima venda. Esperá-lo era mais uma ida ao servidor no "Finalizar".
    if (touchedCash) unawaited(_refreshCashSession());
    if (mounted) setState(() {});
    return true;
  }

  static bool _isCashPayment(Map<String, dynamic> payment) =>
      '${payment['method_type'] ?? payment['payment_method_type'] ?? ''}' ==
      'cash';

  /// Relê o caixa: o saldo da gaveta depois de mexer em dinheiro, e o aviso
  /// de caixa vindo do servidor (fechado aqui ou em outro terminal).
  Future<void> _refreshCashSession() async {
    try {
      cashSession = await api.get(
        '/cash-register/current/',
        query: {
          if (selectedRestaurantId != null) 'restaurant': selectedRestaurantId,
        },
        accessToken: token,
      );
    } on ApiException catch (erro) {
      // Caixa fechado (404) ou com outro (403/409) volta o bloqueio; falha de
      // rede deixa a tela como está e o próximo aviso tenta de novo.
      cashSession = caixaAposRecusa(erro, cashSession);
    }
    if (mounted) setState(() {});
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
      _tirarRecebimentoMontado(payment);
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
    if (completingOrder || _calculandoTotal) return;
    if (remainingTotal > .009) {
      _error(const ApiException('Ainda existe um valor restante para pagar.'));
      return;
    }
    // Venda de total zero (desconto de 100%) conclui sem recebimento nenhum:
    // o documento digitado também precisa entrar.
    if (!await _aplicarDocumentoPendente() || !mounted) return;
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
    _seguirDepoisDePago();
  }
}
