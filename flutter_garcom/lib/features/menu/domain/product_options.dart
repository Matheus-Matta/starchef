/// O que o garçom escolheu lançar no pedido.
class ProductChoice {
  const ProductChoice({
    required this.productId,
    required this.productName,
    required this.quantity,
    this.variationId,
    this.variationName,
    this.addonIds = const [],
    this.note = '',
  });

  final String productId;
  final String productName;
  final int quantity;
  final String? variationId;

  /// Nome da variação escolhida, para a lista de itens a enviar dizer o que
  /// foi escolhido sem uma segunda consulta ao catálogo.
  final String? variationName;
  final List<String> addonIds;
  final String note;
}

/// Variações ativas do produto — mesmo filtro do PDV
/// (`product_config_dialog.dart`): o cadastro pode ter itens desativados sem
/// removê-los do histórico de pedidos antigos.
List<Map<String, dynamic>> activeVariations(Map<String, dynamic> product) =>
    _active(product['variations']);

/// Adicionais ativos do produto, pelo mesmo critério de [activeVariations].
List<Map<String, dynamic>> activeAddons(Map<String, dynamic> product) =>
    _active(product['addons']);

/// Adicional e insumo não são vendidos sozinhos, e produto por kilo depende da
/// balança do balcão — nenhum dos três cabe no lançamento pelo celular.
bool isSellable(Map<String, dynamic> product) =>
    product['product_type'] != 'addon' &&
    product['product_type'] != 'input' &&
    product['pricing_unit'] != 'kg';

/// O cadastro exige escolher a variação deste produto.
bool requiresVariation(Map<String, dynamic> product) =>
    product['requires_variation'] == true &&
    activeVariations(product).isNotEmpty;

List<Map<String, dynamic>> _active(Object? list) => (list as List? ?? const [])
    .whereType<Map>()
    .map(Map<String, dynamic>.from)
    .where((item) => item['is_active'] != false)
    .toList();
