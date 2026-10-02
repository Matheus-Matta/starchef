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
  Future<void> _ensureOrderStarted();

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
    // Não existe mais "escolha o tipo antes de lançar": o rascunho já nasce
    // com destino (balcão, por padrão), e trocá-lo é a barra no topo do
    // carrinho. Este desvio mandava o operador para outra tela no meio do
    // primeiro gesto do atendimento.
    if (_draftIsLive && flowStep != 'order') {
      setState(() => flowStep = 'order');
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
    if (_draftIsLive) {
      _addLineToDraft(
        product,
        quantity: chosen.quantity,
        variationId: chosen.variationId,
        addonIds: chosen.addonIds,
        customerNote: chosen.customerNote,
      );
      return;
    }
    await _work(() async {
      await _ensureOrderStarted();
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
    final selected = await showWeighedProductDialog(
      context,
      product: product,
      scales: scales,
      initialScaleId: scales.length == 1 ? '${scales.first['id']}' : null,
      readScale: (id) =>
          api.get('/scales/$id/latest-reading/', accessToken: token),
    );
    if (selected == null) return;

    final weight = selected.weightKg;
    final reading = selected.scaleReading;
    if (_draftIsLive) {
      _addLineToDraft(
        product,
        quantity: weight,
        customerNote: selected.note,
        weightKg: weight,
        scaleReadingId: reading?['id'] == null ? null : '${reading!['id']}',
      );
      return;
    }
    await _work(() async {
      await _ensureOrderStarted();
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          if (reading != null)
            'scale_reading': reading['id']
          else
            'weight_kg': weight.toStringAsFixed(3),
          'customer_note': selected.note,
          'variations': [],
          'addons': [],
        },
        accessToken: token,
      );
      await _refreshOrder();
    });
  }
}
