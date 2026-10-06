// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O que fazer com o que o código VIROU.
///
/// O despacho por tela fica em `home_page_scan.dart`; aqui estão as ações que
/// ele escolhe. O corte é entre "qual é a regra desta tela" e "como se abre um
/// pedido, se anexa um cartão, se lança um produto" — a primeira muda quando
/// se acrescenta uma tela, as segundas quando muda a API.
mixin _ScanActionsSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  String? get orderType;
  String? get scanningProductId;
  StreamController<void>? get productScanRepeats;
  List<Map<String, dynamic>> get commands;

  Future<void> _openCommand(Map<String, dynamic> command);
  Future<void> _configureProduct(Map<String, dynamic> product);
  bool _conferirComandaLida(String lido, Map<String, dynamic> comanda);
  void _useCommandFromCode(Map<String, dynamic> comanda);

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
    // Onde o leitor só lê comanda, o número aparece já na leitura. Onde ele
    // também lê produto e pedido, só depois de saber que é uma comanda.
    if (onNotFound == null) {
      return mostrandoComandaLida(
        context,
        code,
        () => _resolveAndOpenCommandOrder(code, onNotFound: null),
      );
    }
    return _resolveAndOpenCommandOrder(code, onNotFound: onNotFound);
  }

  Future<void> _resolveAndOpenCommandOrder(
    String code, {
    required VoidCallback? onNotFound,
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
    if (!_conferirComandaLida(code, command)) return;
    final local = commands.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == '${command['id']}',
      orElse: () => null,
    );
    if (onNotFound == null) {
      await _openCommand(local ?? command);
      return;
    }
    if (!mounted) return;
    await mostrandoComandaLida(
      context,
      code,
      () => _openCommand(local ?? command),
    );
  }

  /// A tela de venda: primeiro produto, depois comanda.
  ///
  /// Ler um cartão aqui não fazia nada. A tela só procurava produto, e o
  /// operador que montava o pedido e passava a comanda — o gesto natural de
  /// quem tem o cartão na mão — via a leitura cair no vazio, sem nem um aviso.
  ///
  /// A ordem — produto antes de comanda — é do `CodeLookupService.findForSale`,
  /// com o porquê registrado lá.
  Future<void> _onSaleScreenCode(String code) async {
    final lookup = _codeLookup;
    if (lookup == null) return;

    // O modal de configuração aberto tem prioridade: a leitura repetida do
    // mesmo produto soma lá dentro, e não pode ser reinterpretada como
    // comanda.
    if (scanningProductId != null) {
      await _addProductFromCode(code);
      return;
    }

    final achado = await lookup.findForSale(
      code,
      restaurantId: restaurantId,
      orderType: orderType,
    );
    if (!mounted) return;
    final produto = achado.product;
    if (produto != null) {
      await _configureProduct(produto);
      return;
    }
    final comanda = achado.command;
    if (comanda == null || !_conferirComandaLida(code, comanda)) return;
    await mostrandoComandaLida(
      context,
      code,
      () async => _useCommandFromCode(comanda),
    );
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
}
