part of 'home_page.dart';

/// Entrada: teclado, leitor de código, área de transferência e atalhos.
///
/// Inclui a seleção de item por teclas e o que o Enter confirma em cada tela.
/// Os métodos foram MOVIDOS, não reescritos.
mixin _InputSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  PdvInputRouter get inputRouter;
  TerminalTopology get topology;
  LocalOrderStore get orderStore;
  CodeLookupService? get codeLookup;
  set codeLookup(CodeLookupService? value);

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCommand;
  set selectedCommand(Map<String, dynamic>? value);
  List<Map<String, dynamic>> get orderItems;
  List<Map<String, dynamic>> get commands;
  List<Map<String, dynamic>> get products;
  List<Map<String, dynamic>> get paymentMethods;
  List<Map<String, dynamic>> get registeredPayments;
  set registeredPayments(List<Map<String, dynamic>> value);
  List<Map<String, dynamic>> get visibleCommands;
  List<Map<String, dynamic>> get stagedPayments;
  String? get orderType;
  set orderType(String? value);
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
  String? get selectedPaymentMethod;
  double get paymentValue;
  double get remainingTotal;
  FocusNode get ordersSearchFocus;
  FocusNode get commandSearchFocus;

  Future<void> _load();
  Future<void> _navigateTo(PdvDestination destination);
  Future<void> _refreshOrder();
  void _onCommandSearchSubmitted(String value);
  TextEditingController get ordersSearchController;
  String get orderSearch;
  set orderSearch(String value);
  Future<void> _goHome();
  void _goBack();
  Future<void> _openCommand(Map<String, dynamic> command);
  Future<void> _configureProduct(Map<String, dynamic> product);
  Future<void> _openCashCenter();
  Future<void> _preparePaymentPage();
  // ignore: unused_element_parameter
  Future<void> _printCustomerReceipt([Map<String, dynamic>? selectedOrder]);
  Future<void> _finishOrder();
  Future<void> _completePaidOrder();
  void _addSplitPayment();
  Future<void> _voidItem(Map<String, dynamic> item);
  Future<Map<String, dynamic>> _sendPendingItemsToKitchen(
    List<Map<String, dynamic>> pending,
  );

  // ───────────────────────────────── entrada (teclado, leitor, colar) ──

  /// Em que tela o operador está — é o que decide como um código é lido.
  PdvScreen get _currentScreen {
    if (flowStep == 'scale-workstation') return PdvScreen.scale;
    if (flowStep == 'orders') return PdvScreen.orders;
    if (flowStep == 'payment') return PdvScreen.payment;
    if (activeOrder != null) return PdvScreen.order;
    if (flowStep == 'context' || flowStep == 'table_details') {
      return PdvScreen.context;
    }
    return PdvScreen.home;
  }

  /// O cursor está dentro de um campo de texto?
  ///
  /// Com um campo focado o teclado é dele: o leitor escreve ali como qualquer
  /// digitação, em vez de a tela interpretar o código por conta própria.
  bool get _hasTextFocus {
    final focus = FocusManager.instance.primaryFocus?.context;
    if (focus == null) return false;
    return focus.widget is EditableText ||
        focus.findAncestorWidgetOfExactType<EditableText>() != null;
  }

  /// Há um diálogo aberto por cima desta página?
  ///
  /// A rota da página deixa de ser a corrente quando um modal sobe — é o
  /// sinal mais confiável, e não depende de cada `showDialog` do arquivo
  /// lembrar de avisar.
  bool get _hasModalAbove {
    final route = ModalRoute.of(context);
    return route != null && !route.isCurrent;
  }

  PdvInputContext _readInputContext() => PdvInputContext(
    screen: _currentScreen,
    hasTextFocus: _hasTextFocus,
    hasModal: _hasModalAbove,
    // O único modal que entende código é o de configuração de produto: ler o
    // mesmo item de novo soma quantidade lá dentro.
    modalAcceptsScanner: scanningProductId != null,
    hasOrder: activeOrder != null,
  );

  /// A consulta de códigos, quando o armazenamento local já está ligado.
  ///
  /// Antes do login não há banco local, e ler um código nesse momento não faz
  /// sentido nenhum — daí o nulo em vez de uma exceção.
  CodeLookupService? get _codeLookup {
    final gateway = api.localStore;
    if (gateway == null) return null;
    return codeLookup ??= CodeLookupService(gateway);
  }

  /// Um código chegou — de onde quer que tenha vindo.
  Future<void> _onCodeScanned(ScannedCode scanned) async {
    switch (_currentScreen) {
      case PdvScreen.home:
        await _openOrderFromCommandCode(scanned.value);
      case PdvScreen.context:
        // A busca em memória (por número/código exato da lista já filtrada)
        // continua servindo a aba Comandas, que tem seu próprio campo de
        // busca e convive bem com múltiplos resultados. A aba Mesas não tem
        // campo de busca nenhum, então usa a mesma consulta ao banco local
        // que a tela inicial usa — robusta mesmo com `commands` desatualizado.
        if (orderType == 'command') {
          _onCommandSearchSubmitted(scanned.value);
        } else {
          await _openOrderFromCommandCode(scanned.value);
        }
      case PdvScreen.order:
        await _addProductFromCode(scanned.value);
      case PdvScreen.orders:
        // Bipar uma comanda abre direto o pedido em aberto dela; qualquer
        // outro código (produto, número de pedido) só preenche a busca da
        // lista, como antes.
        await _openOrderFromCommandCode(
          scanned.value,
          onNotFound: () {
            ordersSearchController.text = scanned.value;
            setState(() => orderSearch = scanned.value);
          },
        );
      case PdvScreen.payment:
      case PdvScreen.cash:
      case PdvScreen.settings:
      case PdvScreen.scale:
        break;
    }
  }

  /// Acha a comanda pelo código lido e abre o pedido em aberto dela.
  ///
  /// Usada pela tela inicial, pela aba Mesas e pela lista de Pedidos — sempre
  /// que a tela não tem um jeito melhor de tratar um código que não é
  /// comanda. Sem `onNotFound`, o silêncio é deliberado: um aviso a cada
  /// leitura sem correspondência transformaria uma pilha de cartões
  /// conferidos rapidamente em uma sequência de alertas para fechar.
  ///
  /// Também não procura produto aqui: um EAN lido por engano não pode
  /// disparar uma ação inesperada nessas telas.
  Future<void> _openOrderFromCommandCode(
    String code, {
    VoidCallback? onNotFound,
  }) async {
    final lookup = _codeLookup;
    if (lookup == null) {
      onNotFound?.call();
      return;
    }
    final resolution = await lookup.findCommand(code);
    final command = resolution.command;
    if (command == null) {
      onNotFound?.call();
      return;
    }
    final orderId = '${command['current_order_id'] ?? ''}';
    if (orderId.isEmpty) {
      onNotFound?.call();
      return;
    }
    final local = commands.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == '${command['id']}',
      orElse: () => null,
    );
    await _openCommand(local ?? command);
  }

  /// Edição do pedido: acha o produto e abre a configuração dele.
  Future<void> _addProductFromCode(String code) async {
    final lookup = _codeLookup;
    if (lookup == null) return;
    // Leitura repetida com o modal aberto: soma lá dentro.
    if (scanningProductId != null) {
      final repeated = await lookup.findProduct(
        code,
        restaurantId: restaurantId,
        orderType: orderType,
      );
      if ('${repeated.product?['id'] ?? ''}' == scanningProductId) {
        productScanRepeats?.add(null);
      }
      return;
    }

    final resolution = await lookup.findProduct(
      code,
      restaurantId: restaurantId,
      orderType: orderType,
    );
    final product = resolution.product;
    if (product == null) return;

    // Quem decide entre somar uma unidade e abrir o modal é
    // `_configureProduct`: produto sem escolha soma direto, com variação ou
    // adicional a pergunta continua. Duplicar a regra aqui deixava a leitura
    // do EAN pular as recusas que ela faz (pedido fechado, caixa fechado,
    // produto por peso).
    await _configureProduct(product);
  }

  // Consumido por outra seção via declaração abstrata; o analisador não
  // enxerga a ligação entre mixins.
  // ignore: unused_element
  bool _productHasChoices(Map<String, dynamic> product) {
    bool active(List? list) => (list ?? const []).whereType<Map>().any(
      (item) => item['is_active'] != false,
    );
    return active(product['variations'] as List?) ||
        active(product['addons'] as List?);
  }

  /// Soma uma unidade ao item pendente. O servidor agrupa itens pendentes
  /// iguais, e o armazenamento local passou a agrupar na mesma hora.
  // Consumido por outra seção via declaração abstrata; o analisador não
  // enxerga a ligação entre mixins.
  // ignore: unused_element
  Future<void> _addOneMoreOf(Map<String, dynamic> product) async {
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          'quantity': 1,
          'variations': const [],
          'addons': const [],
          'expected_unit_price': OrderPresenter.expectedUnitPrice(
            product,
          ).toStringAsFixed(2),
          'customer_note': '',
        },
        accessToken: token,
      );
      await _refreshOrder();
    });
  }

  /// Executa a ação de um atalho.
  Future<void> _onShortcut(PdvShortcut shortcut) async {
    switch (shortcut.id) {
      case PdvAction.help:
        await _openHelp();
      case PdvAction.readClipboard:
        await inputRouter.readFromClipboard();
      case PdvAction.home:
      case PdvAction.newSale:
        if (await _confirmLeavingPendingItems()) await _goHome();
      case PdvAction.orders:
        await _navigateTo(PdvDestination.orders);
      case PdvAction.refresh:
        await _load();
      case PdvAction.cashCenter:
        await _openCashCenter();
      case PdvAction.pickCommand:
        setState(() {
          orderType = 'command';
          commandSearch = '';
          flowStep = 'context';
        });
      case PdvAction.back:
        _goBack();
      case PdvAction.focusSearch:
        _focusPageSearch();
      case PdvAction.sendToKitchen:
        await _sendPendingFromShortcut();
      case PdvAction.payment:
        await _preparePaymentPage();
      case PdvAction.printReceipt:
        await _printCustomerReceipt();
      case PdvAction.moveSelectionUp:
        _moveItemSelection(-1);
      case PdvAction.moveSelectionDown:
        _moveItemSelection(1);
      case PdvAction.increaseQuantity:
        await _changeSelectedQuantity(1);
      case PdvAction.decreaseQuantity:
        await _changeSelectedQuantity(-1);
      case PdvAction.removeItem:
        await _removeSelectedItem();
      case PdvAction.confirm:
        await _confirmPrimaryAction();
    }
  }

  /// Confirma o descarte dos recebimentos que ainda não subiram.
  Future<void> _confirmLeavingPayment() async {
    final count = stagedPayments.length;
    final discard = await showDialog<bool>(
      context: context,
      builder: (ctx) => AppDialog(
        title: const Text('Descartar os recebimentos desta tela?'),
        content: Text(
          count == 1
              ? 'Há 1 recebimento montado que ainda não foi enviado. Voltar '
                    'agora o descarta — o pedido continua em aberto.'
              : 'Há $count recebimentos montados que ainda não foram '
                    'enviados. Voltar agora os descarta — o pedido continua '
                    'em aberto.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Continuar recebendo'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Descartar e voltar'),
          ),
        ],
      ),
    );
    if (discard != true || !mounted) return;
    setState(() {
      registeredPayments = registeredPayments
          .where((payment) => payment['_staged'] != true)
          .toList();
      flowStep = 'order';
    });
  }

  /// Sair do pedido com itens ainda não enviados exige confirmação.
  ///
  /// F3 e Ctrl + N ficam ao lado de teclas usadas o tempo todo, e um toque
  /// errado apagaria da tela itens que a cozinha nunca recebeu — sem que
  /// ninguém percebesse até o cliente cobrar.
  Future<bool> _confirmLeavingPendingItems() async {
    if (activeOrder == null) return true;
    final pending = orderItems
        .where((item) => item['status'] == 'pending')
        .length;
    if (pending == 0) return true;
    final answer = await showDialog<bool>(
      context: context,
      builder: (ctx) => AppDialog(
        title: const Text('Sair com itens não enviados?'),
        content: Text(
          pending == 1
              ? 'Há 1 item lançado que ainda não foi para a cozinha. '
                    'Ele continua no pedido, mas você sai da tela dele.'
              : 'Há $pending itens lançados que ainda não foram para a '
                    'cozinha. Eles continuam no pedido, mas você sai da tela '
                    'dele.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Continuar no pedido'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sair mesmo assim'),
          ),
        ],
      ),
    );
    return answer == true;
  }

  // ─────────────────────────────────── seleção de item por teclado ──

  /// A lista de itens na MESMA ordem em que o painel a desenha.
  ///
  /// As setas precisam andar na ordem que o operador vê; percorrer a lista
  /// bruta faria o cursor pular de um bloco para o outro sem motivo aparente.
  List<Map<String, dynamic>> get _itemsInDisplayOrder => [
    ...orderItems.where((item) => item['status'] != 'pending'),
    ...orderItems.where((item) => item['status'] == 'pending'),
  ];

  Map<String, dynamic>? get _selectedOrderItem {
    final id = selectedOrderItemId;
    if (id == null) return null;
    for (final item in orderItems) {
      if ('${item['id']}' == id) return item;
    }
    return null;
  }

  /// Move o cursor. Sem seleção, a primeira seta escolhe a ponta certa da
  /// lista — descer começa no primeiro item, subir no último.
  void _moveItemSelection(int delta) {
    final items = _itemsInDisplayOrder;
    if (items.isEmpty) {
      setState(() => selectedOrderItemId = null);
      return;
    }
    final current = items.indexWhere(
      (item) => '${item['id']}' == selectedOrderItemId,
    );
    final next = current < 0
        ? (delta > 0 ? 0 : items.length - 1)
        : (current + delta).clamp(0, items.length - 1);
    setState(() => selectedOrderItemId = '${items[next]['id']}');
    _revealSelectedItem();
  }

  void _selectOrderItem(Map<String, dynamic> item) {
    setState(() => selectedOrderItemId = '${item['id']}');
  }

  /// Rola a lista até a linha selecionada quando ela sai da área visível.
  void _revealSelectedItem() {
    final id = selectedOrderItemId;
    if (id == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = OrderCartPanel.contextOfItem(id);
      if (target == null) return;
      unawaited(
        Scrollable.ensureVisible(
          target,
          alignment: .5,
          duration: const Duration(milliseconds: 140),
        ),
      );
    });
  }

  /// `+` e `-` sobre o item selecionado.
  ///
  /// Só item pendente: um já despachado descreve o que a cozinha recebeu, e
  /// mudar a quantidade dele reescreveria o passado sem ninguém na produção
  /// ficar sabendo. Chegando a zero, a tecla vira o cancelamento — que exige
  /// motivo e deixa registro, em vez de apagar em silêncio.
  Future<void> _changeSelectedQuantity(int delta) async {
    final item = _selectedOrderItem;
    if (item == null) return;
    await _changeItemQuantity(item, delta);
  }

  /// Soma [delta] unidades a um item. Serve às teclas `+`/`-` e ao contador
  /// que fica no próprio cartão da lista — o mesmo caminho, com as mesmas
  /// recusas, para os dois gestos não divergirem.
  Future<void> _changeItemQuantity(Map<String, dynamic> item, int delta) async {
    if (busy || activeOrder == null) return;
    if ('${item['status'] ?? ''}' != 'pending') {
      _error(
        const ApiException(
          'Este item já foi para a produção. Cancele-o (Delete) se precisar '
          'tirá-lo da conta.',
        ),
      );
      return;
    }
    if ('${item['pricing_unit'] ?? 'unit'}' == 'kg') {
      _error(
        const ApiException(
          'Produto vendido por peso: a quantidade vem da balança.',
        ),
      );
      return;
    }
    final quantity = ValueFormatters.number(item['quantity']) + delta;
    if (quantity <= 0) {
      // Zero é cancelamento, e cancelamento pede motivo e deixa registro.
      await _voidItem(item);
      if (mounted && '${item['id']}' == selectedOrderItemId) {
        setState(() => selectedOrderItemId = null);
      }
      return;
    }
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/${item['id']}/quantity/',
        body: {'quantity': quantity},
        accessToken: token,
      );
      await _refreshOrder();
      return activeOrder ?? <String, dynamic>{};
    });
  }

  /// Delete sobre o item selecionado.
  ///
  /// Reusa o cancelamento normal, que já pede motivo e — para item despachado
  /// — passa pela permissão e pelo cupom de cancelamento na cozinha. Uma tecla
  /// não pode ter um caminho mais curto do que o botão.
  Future<void> _removeSelectedItem() async {
    final item = _selectedOrderItem;
    if (item == null || busy) return;
    await _voidItem(item);
    if (mounted) setState(() => selectedOrderItemId = null);
  }

  // ────────────────────────────────────────────── ação principal (Enter) ──

  /// O que o Enter confirma nesta tela.
  ///
  /// Só chega aqui quando NÃO há modal aberto nem campo focado — nesses dois
  /// casos o Enter pertence a quem tem o foco, e é assim que ele continua
  /// funcionando dentro dos diálogos sem nenhum caso especial.
  Future<void> _confirmPrimaryAction() async {
    switch (_currentScreen) {
      case PdvScreen.order:
        if (activeOrder == null || orderItems.isEmpty) return;
        await _finishOrder();
      case PdvScreen.context:
        // Uma comanda filtrada e só uma: confirmar é abrir. Com várias, o
        // Enter não escolhe por ninguém.
        if (orderType != 'command') return;
        final visible = visibleCommands;
        if (visible.length == 1) await _openCommand(visible.first);
      case PdvScreen.payment:
        await _confirmPaymentFromKeyboard();
      case PdvScreen.home:
      case PdvScreen.orders:
      case PdvScreen.cash:
      case PdvScreen.settings:
      case PdvScreen.scale:
        break;
    }
  }

  /// Enter na tela de pagamento.
  ///
  /// A regra é a mesma do botão, e de propósito: enquanto faltar dado
  /// obrigatório, a tecla não conclui nada. Um Enter que cobra sozinho seria
  /// pior do que um Enter que não faz nada, porque o operador só descobriria
  /// depois — com o cliente já do outro lado do balcão.
  Future<void> _confirmPaymentFromKeyboard() async {
    if (activeOrder == null || busy) return;
    // Já pago por inteiro: confirmar é concluir.
    if (remainingTotal <= .009) {
      await _completePaidOrder();
      return;
    }
    // Falta valor: só registra o recebimento digitado, e só se ele existir e
    // houver forma de pagamento escolhida.
    if (selectedPaymentMethod == null || paymentValue <= 0) return;
    _addSplitPayment();
  }

  /// Leva o cursor para a busca da tela atual.
  void _focusPageSearch() {
    if (_currentScreen == PdvScreen.orders) {
      ordersSearchFocus.requestFocus();
      return;
    }
    if (_currentScreen == PdvScreen.context) {
      commandSearchFocus.requestFocus();
    }
  }

  /// F9: manda para a produção só o que ainda está pendente.
  ///
  /// Sem itens pendentes a tecla não faz nada — e não avisa: apertar F9 duas
  /// vezes é comum, e a segunda não pode virar um alerta.
  Future<void> _sendPendingFromShortcut() async {
    if (activeOrder == null || busy) return;
    final pending = orderItems
        .where((item) => item['status'] == 'pending')
        .toList();
    if (pending.isEmpty) return;
    await _work(() async {
      await _sendPendingItemsToKitchen(pending);
      return activeOrder ?? <String, dynamic>{};
    });
    if (mounted) await _refreshOrder();
  }

  Future<void> _openHelp() async {
    final serial = topology.config;
    await PdvHelpDialog.show(
      context,
      screen: _currentScreen,
      hasOrder: activeOrder != null,
      scannerStatus: ScannerStatus(
        connected: false,
        detail: serial == null
            ? 'A estação de balança é quem cuida do leitor serial.'
            : 'Vincule o leitor serial em Balança rápida › Equipamentos.',
      ),
      lastCode: inputRouter.lastCode,
      onTestCode: _describeCode,
    );
  }

  /// Diz o que ACONTECERIA com um código, sem executar nada.
  Future<String> _describeCode(String code) async {
    final screen = _currentScreen;
    if (!screen.readsCodes) {
      return '${screen.label}: códigos são ignorados aqui, de propósito.';
    }
    final lookup = _codeLookup;
    if (lookup == null) {
      return 'O armazenamento local ainda não está pronto nesta sessão.';
    }
    final product = await lookup.findProduct(
      code,
      restaurantId: restaurantId,
      orderType: orderType,
    );
    if (product.found) {
      return 'Produto "${product.product?['name']}" — encontrado pelo '
          '${product.matchedFieldLabel}.'
          '${screen == PdvScreen.order ? ' Nesta tela, abriria a configuração do item.' : ' Esta tela não lança produtos.'}';
    }
    final command = await lookup.findCommand(code);
    if (command.found) {
      final orderId = '${command.command?['current_order_id'] ?? ''}';
      return 'Comanda ${command.command?['number']} — encontrada pelo '
          '${command.matchedFieldLabel}. '
          '${orderId.isEmpty ? 'Sem pedido em aberto.' : 'Abriria o pedido em aberto dela.'}';
    }
    return 'Nenhuma comanda e nenhum produto com este código. '
        'Na operação, uma leitura assim não faz nada e não mostra aviso.';
  }
}
