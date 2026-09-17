// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Lançar um produto no pedido: variações, adicionais e pesagem.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _ProductSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;

  Map<String, dynamic>? get activeOrder;
  Map<String, dynamic>? get cashSession;
  Map<String, dynamic>? get selectedCommand;
  String? get scanningProductId;
  set scanningProductId(String? value);
  StreamController<void>? get productScanRepeats;
  set productScanRepeats(StreamController<void>? value);
  String get flowStep;
  set flowStep(String value);
  String? get orderType;
  set orderType(String? value);
  String get commandSearch;
  set commandSearch(String value);

  Future<void> _refreshOrder();
  bool _productHasChoices(Map<String, dynamic> product);
  Future<void> _addOneMoreOf(Map<String, dynamic> product);

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
}
