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

  Future<void> _goHome();
  void _refreshSuggestedPaymentAmount();
  void _warnLocalOrderData();
  bool _productHasChoices(Map<String, dynamic> product);
  Future<void> _addOneMoreOf(Map<String, dynamic> product);
  List<Map<String, dynamic>> get products;
  Future<void> _paymentDialog();

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

  Future<Map<String, dynamic>?> _chooseCustomer(String type) async {
    List<Map<String, dynamic>> customers;
    try {
      customers = await _list(
        '/customers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 300,
        },
      );
    } catch (error) {
      if (mounted) _error(error);
      return null;
    }
    if (!mounted) return null;
    var search = '';
    return showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (context) => StatefulBuilder(
        builder: (context, update) {
          final filtered = customers.where((customer) {
            final term = search.trim().toLowerCase();
            return term.isEmpty ||
                '${customer['name']} ${customer['phone']} ${customer['document'] ?? ''}'
                    .toLowerCase()
                    .contains(term);
          }).toList();
          return AppDialog(
            title: Text(
              type == 'delivery'
                  ? 'Cliente do delivery'
                  : 'Cliente da retirada',
            ),
            content: SizedBox(
              width: 620,
              height: 480,
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          autofocus: true,
                          onChanged: (value) => update(() => search = value),
                          decoration: const InputDecoration(
                            labelText: 'Buscar cliente',
                            hintText: 'Nome, telefone ou CPF',
                            prefixIcon: Icon(Icons.search),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.icon(
                        onPressed: () async {
                          final created = await _createCustomerDialog();
                          if (created != null && context.mounted) {
                            customers = [created, ...customers];
                            update(() {});
                            Navigator.pop(context, created);
                          }
                        },
                        icon: const Icon(Icons.person_add_alt_1),
                        label: const Text('Novo cliente'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: filtered.isEmpty
                        ? const Center(
                            child: Text(
                              'Nenhum cliente encontrado. Cadastre um novo cliente.',
                              textAlign: TextAlign.center,
                            ),
                          )
                        : ListView.separated(
                            itemCount: filtered.length,
                            separatorBuilder: (_, _) =>
                                const Divider(height: 1),
                            itemBuilder: (_, index) {
                              final customer = filtered[index];
                              return ListTile(
                                leading: const CircleAvatar(
                                  child: Icon(Icons.person_outline),
                                ),
                                title: Text('${customer['name']}'),
                                subtitle: Text('${customer['phone']}'),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () => Navigator.pop(context, customer),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Voltar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<Map<String, dynamic>?> _createCustomerDialog() async {
    final formKey = GlobalKey<FormState>();
    final name = TextEditingController();
    final phone = TextEditingController();
    final email = TextEditingController();
    final document = TextEditingController();
    final notes = TextEditingController();
    var saving = false;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AppDialog(
          title: const Text('Cadastrar cliente'),
          content: SizedBox(
            width: 560,
            child: Form(
              key: formKey,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextFormField(
                      controller: name,
                      autofocus: true,
                      decoration: const InputDecoration(
                        labelText: 'Nome completo',
                        helperText: 'Nome usado para identificar o cliente.',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Informe o nome do cliente.'
                          : null,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: 'Telefone',
                        helperText: 'Número para contato sobre o pedido.',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Informe o telefone.'
                          : null,
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: email,
                            keyboardType: TextInputType.emailAddress,
                            decoration: const InputDecoration(
                              labelText: 'E-mail',
                              helperText: 'Opcional',
                            ),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: TextFormField(
                            controller: document,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'CPF',
                              helperText: 'Opcional',
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: notes,
                      maxLines: 2,
                      decoration: const InputDecoration(
                        labelText: 'Observações internas',
                        helperText:
                            'Informações visíveis somente para a equipe.',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(context),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: saving
                  ? null
                  : () async {
                      if (!formKey.currentState!.validate()) return;
                      update(() => saving = true);
                      try {
                        final customer = await api.post(
                          '/customers/',
                          body: {
                            'restaurant': restaurantId,
                            'name': name.text.trim(),
                            'phone': phone.text.trim(),
                            'email': email.text.trim(),
                            'document': document.text.trim(),
                            'internal_notes': notes.text.trim(),
                            'is_active': true,
                          },
                          accessToken: token,
                        );
                        if (context.mounted) Navigator.pop(context, customer);
                      } catch (error) {
                        if (context.mounted) _error(error);
                        update(() => saving = false);
                      }
                    },
              icon: saving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: const Text('Cadastrar e selecionar'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    phone.dispose();
    email.dispose();
    document.dispose();
    notes.dispose();
    return result;
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
        .where((item) => item['status'] != 'voided')
        .toList();
    // O total pode ter mudado aqui — a taxa de serviço do fechamento chega
    // pela sincronização, e é depois desta leitura que ela aparece.
    if (flowStep == 'payment') _refreshSuggestedPaymentAmount();
    if (mounted) setState(() {});
  }

  // Consumido por outra seção via declaração abstrata; o analisador não
  // enxerga a ligação entre mixins.
  // ignore: unused_element
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

  Future<void> _configureProduct(Map<String, dynamic> product) async {
    if (const {
      'paid',
      'cancelled',
      'refunded',
    }.contains('${activeOrder?['status']}')) {
      _error(
        const ApiException(
          'Este pedido já foi concluído e está disponível somente para consulta.',
        ),
      );
      return;
    }
    if (cashSession == null) {
      _error(
        const ApiException('Abra o caixa antes de iniciar pedidos no PDV.'),
      );
      return;
    }
    if (activeOrder == null) {
      setState(() {
        orderType = 'command';
        commandSearch = '';
        flowStep = 'context';
      });
      return;
    }
    if (!mounted) return;
    if (isProductSoldByWeight(product)) {
      await _weighProduct(product);
      return;
    }
    // Produto sem variação e sem adicional não tem NADA a perguntar: clicar
    // nele na lista (ou bipar o EAN) soma uma unidade direto, e o ajuste fino
    // fica no contador do próprio cartão, na lista do pedido. O modal existia
    // para escolher, e abrir uma janela de confirmação para um refrigerante
    // custava dois gestos por unidade num balcão com fila.
    if (!_productHasChoices(product)) {
      await _addOneMoreOf(product);
      return;
    }
    // Enquanto este modal estiver aberto, ler o MESMO produto de novo soma
    // quantidade aqui dentro em vez de abrir um segundo modal por cima.
    //
    // O `finally` não é zelo: se o diálogo falhasse com a marca ligada, toda
    // leitura seguinte seria interpretada como "repetição do produto X" e
    // nenhum outro item entraria no pedido.
    final repeats = StreamController<void>.broadcast();
    ProductConfigResult? config;
    try {
      productScanRepeats = repeats;
      scanningProductId = '${product['id']}';
      config = await showProductConfigDialog(
        context,
        product,
        repeatedScans: repeats.stream,
      );
    } finally {
      scanningProductId = null;
      productScanRepeats = null;
      await repeats.close();
    }
    if (config == null) return;
    // Cópia não-nula: o `finally` acima impede o compilador de promover o tipo.
    final chosen = config;
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          'quantity': chosen.quantity.round(),
          'variations': chosen.variationId == null ? [] : [chosen.variationId],
          'addons': chosen.addonIds,
          'expected_unit_price': OrderPresenter.expectedUnitPrice(
            product,
            variationIds: chosen.variationId == null
                ? const []
                : [chosen.variationId!],
            addonIds: chosen.addonIds,
          ).toStringAsFixed(2),
          'customer_note': chosen.customerNote,
        },
        accessToken: token,
      );
      // O item já foi lançado e os totais recalculados pelo
      // `OrderRepository`; a tela apenas relê o pedido do banco local.
      await _refreshOrder();
    });
  }

  Future<void> _weighProduct(Map<String, dynamic> product) async {
    final scales = await _list(
      '/scales/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    );
    if (!mounted) return;
    String? scaleId = scales.length == 1 ? '${scales.first['id']}' : null;
    Map<String, dynamic>? reading;
    double weight = 0;
    bool readingScale = false;
    String readingMessage = scales.isEmpty
        ? 'Nenhuma balança ativa cadastrada.'
        : 'Selecione a balança e solicite a leitura.';
    final manualWeight = TextEditingController();
    final note = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => CallbackShortcuts(
          bindings: {
            // Enter lança o item pesado, a mesma condição do botão. O atalho
            // precisa do nó de foco abaixo dele: senão o foco fica no escopo
            // da rota e a tecla passa por cima sem tocar em nada.
            for (final key in const [
              LogicalKeyboardKey.enter,
              LogicalKeyboardKey.numpadEnter,
            ])
              SingleActivator(key): () {
                if (weight > 0) Navigator.pop(context, true);
              },
          },
          child: Focus(
            autofocus: true,
            child: AppDialog(
              title: Row(
                children: [
                  const Icon(Icons.scale_outlined),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      '${product['name']} · ${_money(product['current_price'])}/kg',
                    ),
                  ),
                ],
              ),
              content: SizedBox(
                width: 460,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<String?>(
                      initialValue: scaleId,
                      isExpanded: true,
                      decoration: const InputDecoration(
                        labelText: 'Balança',
                        helperText:
                            'Selecione o equipamento que realizará a pesagem.',
                      ),
                      items: scales
                          .map(
                            (scale) => DropdownMenuItem(
                              value: '${scale['id']}',
                              child: Text(
                                '${scale['name']} · ${scale['port'] ?? scale['protocol'] ?? ''}',
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (value) => update(() {
                        scaleId = value;
                        reading = null;
                        weight = 0;
                        readingMessage =
                            'Clique em “Ler balança” para buscar o peso.';
                      }),
                    ),
                    const SizedBox(height: 18),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(vertical: 22),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surfaceContainer,
                        borderRadius: AppTheme.radius,
                        border: Border.all(
                          color: weight > 0
                              ? Theme.of(context).colorScheme.primary
                              : Theme.of(context).dividerColor,
                        ),
                      ),
                      child: Column(
                        children: [
                          Text(
                            weight.toStringAsFixed(3),
                            style: TextStyle(
                              fontSize: 42,
                              fontWeight: FontWeight.w900,
                              color: weight > 0
                                  ? Theme.of(context).colorScheme.primary
                                  : Theme.of(
                                      context,
                                    ).colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const Text(
                            'kg',
                            style: TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      readingMessage,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: scaleId == null || readingScale
                                ? null
                                : () async {
                                    update(() => readingScale = true);
                                    try {
                                      final result = await api.get(
                                        '/scales/$scaleId/latest-reading/',
                                        accessToken: token,
                                      );
                                      final value = _number(
                                        result['net_weight_kg'] ??
                                            result['weight_kg'],
                                      );
                                      update(() {
                                        reading = result;
                                        weight = value;
                                        manualWeight.clear();
                                        readingMessage =
                                            result['is_stable'] == false
                                            ? 'Leitura recebida, mas ainda instável.'
                                            : 'Leitura estável recebida da balança.';
                                      });
                                    } on ApiException catch (error) {
                                      update(
                                        () => readingMessage = error.message,
                                      );
                                      if (mounted) {
                                        showAppError(this.context, error);
                                      }
                                    } finally {
                                      update(() => readingScale = false);
                                    }
                                  },
                            icon: readingScale
                                ? const SizedBox(
                                    width: 17,
                                    height: 17,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.refresh),
                            label: Text(
                              readingScale ? 'Lendo...' : 'Ler balança',
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: manualWeight,
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true,
                            ),
                            decoration: const InputDecoration(
                              labelText: 'Peso manual',
                              suffixText: 'kg',
                            ),
                            onChanged: (value) => update(() {
                              reading = null;
                              weight =
                                  double.tryParse(value.replaceAll(',', '.')) ??
                                  0;
                              readingMessage = weight > 0
                                  ? 'Peso informado manualmente.'
                                  : 'Leia a balança ou informe o peso.';
                            }),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: note,
                      maxLines: 2,
                      decoration: const InputDecoration(
                        labelText: 'Observação',
                        hintText: 'Ex.: retirar excesso de gordura',
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Total estimado',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          _money(weight * _number(product['current_price'])),
                          style: const TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Cancelar'),
                ),
                FilledButton(
                  onPressed: weight > 0
                      ? () => Navigator.pop(context, true)
                      : null,
                  child: const Text('Adicionar ao pedido (Enter)'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (accepted != true) return;
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          if (reading != null)
            'scale_reading': reading!['id']
          else
            'weight_kg': weight.toStringAsFixed(3),
          'customer_note': note.text.trim(),
          'variations': [],
          'addons': [],
        },
        accessToken: token,
      );
      await _refreshOrder();
    });
  }

  Future<void> _voidItem(Map<String, dynamic> item) async {
    // Item já enviado à cozinha: o cancelamento não é só tirar da conta, sai
    // um cupom na impressora do setor para a produção parar. Avisar antes
    // evita o caixa descobrir isso pelo barulho da impressora.
    final inProduction = '${item['status']}' != 'pending';
    final reason = await ItemVoidReasonDialog.show(
      context,
      itemName: '${item['product_name'] ?? 'Item do pedido'}',
      title: inProduction ? 'Cancelar item em produção' : 'Remover item',
      confirmLabel: inProduction ? 'Cancelar e avisar cozinha' : 'Remover item',
      warning: inProduction
          ? 'Este item já foi enviado para a cozinha. Uma nota de '
                'cancelamento será impressa no setor que o recebeu.'
          : null,
    );
    if (reason == null || !mounted) return;

    await _work(() async {
      final response = await api.delete(
        '/orders/${activeOrder!['id']}/items/${item['id']}/void/',
        body: {'reason': reason},
        accessToken: token,
      );
      // Item que já estava na produção precisa de cupom no setor para a
      // cozinha parar de fazê-lo. Quem imprime segue a mesma regra da comanda:
      // se a operação subiu, o backend cria o `PrintJob`; se ficou na fila,
      // quem imprime é este terminal — senão o prato continuaria sendo feito
      // depois de o cliente desistir.
      if (inProduction) {
        await _printCancellationIfQueued(item, reason, response);
      }
      await _refreshOrder();
    });
  }

  /// Quem imprime é o servidor (ou o Caixa Principal, pelo relay)?
  ///
  /// Só quando a operação chega ao destino dentro da janela: aí o `PrintJob`
  /// existe lá e sair papel aqui dobraria o cupom.
  ///
  /// **Um Caixa Secundário nunca espera essa janela.** A impressora é dele, o
  /// cupom ele sabe montar, e o cliente está na frente dele — mandar a
  /// impressão para o Principal faria o papel sair na outra ponta da loja. Ele
  /// vai direto reivindicar e imprimir; se a operação já tiver subido, a
  /// reivindicação falha e o backend assume, que é a mesma rede de segurança
  /// de sempre.
  Future<bool> _serverPrintsInstead(String operationId) async {
    if (isSecondaryStation) return false;
    return api.awaitDelivery(
      operationId,
      timeout: api.syncStatus.hasConnection
          ? const Duration(seconds: 3)
          : const Duration(milliseconds: 400),
    );
  }

  /// Imprime o cupom de cancelamento aqui quando a operação não chegou ao
  /// servidor.
  ///
  /// Reivindica a impressão marcando o corpo AINDA enfileirado antes de mandar
  /// papel: se a operação subir nesse instante, a marcação falha e quem
  /// imprime é o backend. É a mesma trava que impede a comanda de cozinha de
  /// sair duas vezes.
  Future<void> _printCancellationIfQueued(
    Map<String, dynamic> item,
    String reason,
    Map<String, dynamic> response,
  ) async {
    final operationId = '${response['_sync_operation_id'] ?? ''}';
    if (operationId.isEmpty) return;
    if (await _serverPrintsInstead(operationId)) return;
    if (!await api.patchQueuedBody(operationId, {'offline_printed': true})) {
      return;
    }
    final printed = await _printCancellationTicket(item, reason);
    if (!printed) {
      await api.patchQueuedBody(operationId, {'offline_printed': false});
    }
  }

  /// Monta e imprime o cupom de cancelamento nas impressoras do setor do
  /// produto. Devolve `true` se pelo menos uma aceitou.
  Future<bool> _printCancellationTicket(
    Map<String, dynamic> item,
    String reason,
  ) async {
    final order = activeOrder;
    if (order == null) return false;
    final text = LocalPrintRenderer.cancellationTicket(
      order: order,
      item: item,
      reason: reason,
      table: selectedTable,
      command: selectedCommand,
      operatorName: widget.controller.session?.user.name ?? '',
    );
    final product = products.cast<Map<String, dynamic>?>().firstWhere(
      (candidate) => '${candidate?['id']}' == '${item['product']}',
      orElse: () => null,
    );
    final sector = '${product?['sector'] ?? ''}';
    var printed = false;
    for (final printer in await _list(
      '/printers/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    )) {
      // Mesma regra da comanda: o cupom sai no setor que recebeu o item. Um
      // produto sem setor, ou um setor sem impressora, simplesmente não gera
      // cupom — sem erro, como no backend.
      if (sector.isEmpty || '${printer['sector'] ?? ''}' != sector) continue;
      try {
        // O cupom entra na fila local: mesmo que esta impressora esteja sem
        // papel agora, ele sai quando ela voltar.
        final cancelPrinter = KitchenCancelPrinter(
          PrinterDevice.fromJson(printer),
          runtime: deviceAgent.printing,
        );
        if ((await deviceAgent.submit(
          cancelPrinter,
          cancelPrinter.compose(content: text),
        )).accepted) {
          printed = true;
        }
      } catch (_) {
        // Outra impressora do setor ainda pode aceitar.
      }
    }
    return printed;
  }

  Future<void> _cancelOrder() async {
    final order = activeOrder;
    if (order == null ||
        const {
          'paid',
          'cancelled',
          'refunded',
        }.contains('${order['status']}')) {
      return;
    }

    final reason = await ItemVoidReasonDialog.show(
      context,
      itemName: 'Pedido #${order['sequence']}',
      title: 'Cancelar pedido',
      confirmLabel: 'Continuar',
    );
    if (!mounted || reason == null) return;

    String? cashPassword;
    String? authorizationUsername;
    String? authorizationPassword;
    final authorized = await showSupervisorCloseDialog(
      context: context,
      title: 'Autorizar cancelamento',
      description:
          'Confirme com a senha de operação do restaurante ou com o login '
          'de um administrador/usuário que tenha permissão para cancelar pedidos.',
      confirmLabel: 'Cancelar pedido',
      cancelLabel: 'Voltar',
      confirmIcon: Icons.cancel_outlined,
      credentialRoleLabel: 'usuário autorizado',
      verifyPassword: (password) async {
        final valid = await widget.controller.verifySupervisorClosePassword(
          password,
        );
        if (valid) cashPassword = password;
        return valid;
      },
      verifyAdminCredentials: (username, password) async {
        final failure = await widget.controller
            .verifyOrderCancellationCredentials(username, password);
        if (failure == null) {
          authorizationUsername = username;
          authorizationPassword = password;
        }
        return failure;
      },
      onInvalidPassword: () => widget.controller.refreshSupervisorPassword(
        restaurantId: restaurantId,
      ),
    );
    if (!mounted ||
        !authorized ||
        '${activeOrder?['id']}' != '${order['id']}') {
      return;
    }

    final cancelled = await _work(
      () => api.post(
        '/orders/${order['id']}/cancel/',
        body: {
          'reason': reason,
          'cash_password': ?cashPassword,
          'authorization_username': ?authorizationUsername,
          'authorization_password': ?authorizationPassword,
        },
        accessToken: token,
      ),
      errorTitle: 'Não foi possível cancelar o pedido',
    );
    if (!mounted || cancelled == null) return;

    final scope = api.sessionScope;
    if (scope != null) {
      await orderStore.saveFromServer(cancelled, scope: scope);
    }
    if (!mounted) return;
    await _goHome();
  }

  /// Envia os itens pendentes para produção. Quando a rede está fora, imprime
  /// a comanda direto na impressora do setor em vez de esperar o backend
  /// renderizar o `PrintJob` — a cozinha não pode esperar a internet voltar
  /// pra saber que tem pedido novo.
  ///
  /// `offline_printed` só acompanha o envio se a comanda tiver saído mesmo:
  /// essa flag faz o backend registrar os `PrintJob` como já impressos, então
  /// mandá-la depois de uma impressão que falhou deixaria a cozinha sem
  /// comanda nenhuma — nem agora, nem quando a fila sincronizasse.
  ///
  /// A condição é `phase == offline`, e não "sem conexão": `unknown` (antes da
  /// primeira resposta) e `degraded` (servidor instável, mas respondendo)
  /// também contam como "sem conexão" e levavam a imprimir aqui um pedido que
  /// o backend ia imprimir de novo — duas comandas para a mesma rodada.
  Future<Map<String, dynamic>> _sendPendingItemsToKitchen(
    List<Map<String, dynamic>> pendingItems,
  ) async {
    final batchSerial = OrderPresenter.generateBatchSerial();
    final response = await api.post(
      '/orders/${activeOrder!['id']}/send-to-kitchen/',
      body: {'client_batch_serial': batchSerial},
      accessToken: token,
    );
    final operationId = '${response['_sync_operation_id'] ?? ''}';
    AppLogger.instance.info(
      'comanda_envio',
      data: {
        'pedido': '${activeOrder?['id']}',
        'itens_pendentes': pendingItems.length,
        'lote': batchSerial,
        'na_fila': operationId.isNotEmpty,
        'conexao': api.syncStatus.phase.name,
      },
    );
    // Sem operação na fila, quem executou foi o servidor (ou o Caixa
    // Principal, num caixa secundário): o `PrintJob` já existe lá.
    if (operationId.isEmpty) {
      AppLogger.instance.info(
        'comanda_impressao_do_servidor',
        data: {'motivo': 'operacao entregue direto, o PrintJob e de la'},
      );
      return response;
    }

    // Quem imprime a comanda não pode ser decidido por um palpite sobre a
    // conexão. Antes a escolha era feita ANTES do POST, olhando o último
    // estado conhecido da rede; com o PDV offline-first toda escrita passa
    // pela fila, e um estado velho levava aos dois piores resultados
    // possíveis: duas comandas para a mesma rodada, ou nenhuma. Agora a
    // pergunta é factual — a operação chegou ao servidor?
    // Com a rede de pé, três segundos são de sobra para a fila entregar. Com
    // ela reconhecidamente fora, esperar tanto só atrasaria a cozinha — mas a
    // pergunta continua sendo feita, porque o indicador pode estar um
    // instante atrás da realidade.
    if (await _serverPrintsInstead(operationId)) {
      AppLogger.instance.info(
        'comanda_impressao_do_servidor',
        data: {
          'motivo': 'a operacao subiu dentro da janela',
          'operacao': operationId,
        },
      );
      return response;
    }

    // Ela continua na fila. Reivindica a impressão marcando o corpo ANTES de
    // imprimir: se a operação subir neste instante, a marcação falha e quem
    // imprime é o backend. Sem isso, a janela entre imprimir e marcar deixava
    // sair a segunda comanda.
    final claimed = await api.patchQueuedBody(operationId, {
      'offline_printed': true,
    });
    if (!claimed) {
      AppLogger.instance.info(
        'comanda_impressao_do_servidor',
        data: {
          'motivo': 'a operacao subiu enquanto este terminal reivindicava',
          'operacao': operationId,
        },
      );
      return response;
    }

    final printed = await _printKitchenTicketsOffline(
      pendingItems,
      batchSerial,
    );
    if (!printed) {
      AppLogger.instance.warning(
        'comanda_devolvida_ao_backend',
        data: {
          'operacao': operationId,
          'motivo': 'nenhuma impressora aceitou o cupom neste terminal',
        },
      );
      // Não saiu papel aqui. Devolve a impressão ao backend, senão a cozinha
      // ficaria sem comanda agora e também quando a fila sincronizasse.
      await api.patchQueuedBody(operationId, {'offline_printed': false});
    }
    return response;
  }

  /// Monta e imprime a comanda localmente. Devolve `true` se pelo menos uma
  /// impressora aceitou o cupom.
  Future<bool> _printKitchenTicketsOffline(
    List<Map<String, dynamic>> pendingItems,
    String batchSerial,
  ) async {
    // As impressoras vêm da lista que o agente mantém em memória: reler
    // `/printers/` aqui só funcionaria se aquela consulta exata já estivesse
    // no cache de respostas, o que não se pode assumir com a rede fora.
    final printersForTickets = await deviceAgent.ensurePrinters();
    final user = widget.controller.session?.user;
    final plan = OrderPresenter.buildOfflineKitchenTickets(
      order: activeOrder,
      table: selectedTable,
      command: selectedCommand,
      pendingItems: pendingItems,
      products: products,
      printers: printersForTickets,
      batchSerial: batchSerial,
      operatorName: (user?.name ?? '').trim().isNotEmpty
          ? user!.name
          : (user?.username ?? ''),
    );
    final tickets = plan.tickets;
    // A escolha da impressora pelo setor do produto é silenciosa por
    // natureza: item sem setor e setor sem impressora não geram papel nem
    // erro. Esta linha é o que transforma "não imprimiu e não avisou" em algo
    // que se lê no terminal.
    AppLogger.instance.info('comanda_roteamento', data: plan.toLog());
    var printedAny = false;
    Object? lastFailure;
    for (final ticket in tickets) {
      try {
        // Pela fila local: uma impressora sem papel agora não perde a
        // comanda — ela sai assim que o papel voltar, sem depender de um
        // evento do servidor que, offline, nunca chega.
        // `accepted`, não `printed`: com o cupom na fila, este terminal já é
        // o responsável — mesmo que a impressora só aceite daqui a pouco.
        final kitchenPrinter = KitchenPrinter(
          PrinterDevice.fromJson(ticket.printer),
          runtime: deviceAgent.printing,
        );
        if ((await deviceAgent.submit(
          kitchenPrinter,
          kitchenPrinter.compose(content: ticket.text),
        )).accepted) {
          printedAny = true;
        }
      } catch (error) {
        // Uma impressora falhar não pode travar as outras.
        lastFailure = error;
      }
    }
    if (!mounted || printedAny) return printedAny;
    // A mensagem precisa dizer o que de fato impediu a impressão: culpar a
    // internet quando o problema é roteamento de setor manda o caixa
    // procurar no lugar errado.
    showAppToast(
      context,
      switch ((tickets.isEmpty, lastFailure)) {
        (true, _) =>
          'Nenhuma impressora de setor atende os itens deste pedido. '
              'Confira o setor dos produtos e o setor das impressoras em '
              'Configurações e avise a cozinha manualmente.',
        (false, final failure?) =>
          'A comanda não pôde ser enviada à impressora do setor: $failure. '
              'Avise a cozinha manualmente.',
        _ =>
          'A comanda não pôde ser impressa agora. Avise a cozinha '
              'manualmente.',
      },
      title: 'Comanda não impressa',
      severity: AppErrorSeverity.warning,
    );
    return false;
  }

  Future<void> _finishOrder() async {
    if (activeOrder == null || orderItems.isEmpty) return;
    var chargeService = activeOrder?['service_fee_enabled'] != false;
    final nextStep = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AppDialog(
          title: const Text('Revisar pedido'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Subtotal', style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 4),
                Text(
                  _money(activeOrder?['subtotal']),
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 12),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: chargeService,
                  onChanged: (value) =>
                      setDialogState(() => chargeService = value ?? true),
                  title: const Text('Cobrar taxa de serviço'),
                  subtitle: const Text(
                    'Desmarque para retirar a taxa deste pedido.',
                  ),
                ),
                if (chargeService && defaultServiceFeePercent > 0) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Taxa estimada (${defaultServiceFeePercent.toStringAsFixed(2).replaceAll('.', ',')}%): '
                    '${_money(_number(activeOrder?['subtotal']) * defaultServiceFeePercent / 100)}',
                  ),
                ],
                const SizedBox(height: 8),
                Text(
                  'Total estimado: ${_money(_number(activeOrder?['subtotal']) + (chargeService ? _number(activeOrder?['subtotal']) * defaultServiceFeePercent / 100 : 0) + _number(activeOrder?['delivery_fee']) - _number(activeOrder?['discount']))}',
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Voltar'),
            ),
            OutlinedButton.icon(
              onPressed: () => Navigator.pop(context, 'later'),
              icon: const Icon(Icons.schedule),
              label: const Text('Pagar depois'),
            ),
            // Sem `payments.manage`, o operador só pode mandar para a cozinha
            // e deixar o recebimento para quem tem a permissão de caixa.
            if (widget.controller.session!.user.canProcessPayments)
              FilledButton(
                onPressed: () => Navigator.pop(context, 'payment'),
                child: const Text('Ir para pagamento'),
              ),
          ],
        ),
      ),
    );
    if (nextStep == null) return;
    // "Pagar depois" manda os itens para a produção e devolve o operador ao
    // pedido: o cliente segue consumindo, então fechar aqui (status
    // `aguardando pagamento`) travaria o lançamento de novos itens. O
    // fechamento acontece só no caminho do pagamento.
    if (nextStep == 'later') {
      await _work(() async {
        final pending = orderItems
            .where((item) => item['status'] == 'pending')
            .toList();
        if (pending.isEmpty) return <String, dynamic>{};
        // O `OrderRepository` já marcou a rodada como enviada e gravou; a
        // tela relê logo abaixo.
        await _sendPendingItemsToKitchen(pending);
        return activeOrder ?? <String, dynamic>{};
      });
      if (!mounted) return;
      await _refreshOrder();
      if (mounted) setState(() => flowStep = 'order');
      return;
    }
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
      activeOrder = await api.post(
        '/orders/${activeOrder!['id']}/close/',
        body: {
          'discount': activeOrder?['discount'] ?? 0,
          'service_fee_enabled': chargeService,
        },
        accessToken: token,
      );
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
