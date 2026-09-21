// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O carrinho que ainda não existe no servidor.
///
/// O posto abre direto no catálogo e passar produtos não cria nada. O pedido
/// nasce nos DOIS gestos que precisam dele: enviar à cozinha e ir para o
/// pagamento — como sempre funcionou o pedido de balcão.
///
/// Antes, o primeiro produto já abria o pedido, e escolher a comanda 13 pelo
/// caminho antigo ocupava o cartão na hora. Desistir no meio deixava para trás
/// um pedido vazio que alguém tinha de cancelar e uma comanda presa.
///
/// Este mixin é a ponte entre [OrderDraftCart] (o que o operador montou) e o
/// resto da tela, que só sabe trabalhar com pedido de verdade. Depois da
/// materialização nada aqui é consultado: os caminhos de pagamento, fiscal,
/// impressão e conta agrupada continuam falando com `activeOrder`, como antes.
mixin _DraftSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  List<Map<String, dynamic>> get orderItems;

  /// O rascunho está no ar: catálogo aberto, sem pedido no servidor.
  @override
  bool get _draftIsLive => activeOrder == null;

  /// O que o carrinho desenha: as linhas do rascunho enquanto não há pedido, e
  /// os itens de verdade depois.
  @override
  List<Map<String, dynamic>> get _cartItems =>
      _draftIsLive ? draft.cartItems : orderItems;

  /// Inclui um produto no rascunho, no formato que a materialização vai usar.
  ///
  /// Cada caminho de lançamento (clique, leitor de código, configuração com
  /// variações, pesagem) chama daqui em vez de repetir a montagem da linha:
  /// quatro cópias do mesmo mapa divergem, e uma que esquecesse o
  /// `customer_note` perderia a observação do cliente só naquele gesto.
  @override
  void _addLineToDraft(
    Map<String, dynamic> product, {
    double quantity = 1,
    String? variationId,
    List<String> addonIds = const [],
    String customerNote = '',
    double? weightKg,
    String? scaleReadingId,
  }) {
    setState(() {
      draft.add(
        OrderDraftLine(
          id: '',
          productId: '${product['id']}',
          productName: '${product['name'] ?? ''}',
          quantity: quantity,
          unitPrice: OrderPresenter.expectedUnitPrice(
            product,
            variationIds: variationId == null ? const [] : [variationId],
            addonIds: addonIds,
          ),
          variationId: variationId,
          addonIds: addonIds,
          customerNote: customerNote,
          weightKg: weightKg,
          scaleReadingId: scaleReadingId,
          pricingUnit: '${product['pricing_unit'] ?? 'unit'}',
        ),
      );
    });
  }

  /// Muda a quantidade de uma linha do rascunho — sem ida ao servidor.
  @override
  void _changeDraftQuantity(String id, double quantity) =>
      setState(() => draft.changeQuantity(id, quantity));

  @override
  void _removeDraftLine(String id) => setState(() => draft.remove(id));
}
