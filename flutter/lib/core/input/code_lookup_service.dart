import '../data/entity_catalog.dart';
import '../data/entity_repository.dart';
import '../data/offline_first_gateway.dart';

/// O que um código lido representa, depois de consultado.
class CodeResolution {
  const CodeResolution._({
    required this.kind,
    this.command,
    this.product,
    this.matchedField = '',
  });

  const CodeResolution.none() : this._(kind: CodeResolutionKind.none);

  const CodeResolution.command(Map<String, dynamic> value, {String field = ''})
    : this._(
        kind: CodeResolutionKind.command,
        command: value,
        matchedField: field,
      );

  const CodeResolution.product(Map<String, dynamic> value, {String field = ''})
    : this._(
        kind: CodeResolutionKind.product,
        product: value,
        matchedField: field,
      );

  final CodeResolutionKind kind;
  final Map<String, dynamic>? command;
  final Map<String, dynamic>? product;

  /// Campo que casou (`ean`, `internal_code`, `code`, `number`).
  final String matchedField;

  bool get found => kind != CodeResolutionKind.none;

  String get matchedFieldLabel => switch (matchedField) {
    'ean' => 'código de barras',
    'internal_code' => 'código interno',
    'code' => 'código da comanda',
    'number' => 'número da comanda',
    _ => 'código',
  };
}

enum CodeResolutionKind { none, command, product }

/// Traduz um código lido em uma comanda ou em um produto.
///
/// A consulta é SEMPRE local primeiro: é o SQLite do Caixa Principal que
/// responde, e é por isso que o leitor continua funcionando com a internet
/// fora. Perguntar ao servidor a cada bipe também colocaria a latência da rede
/// entre o operador e a próxima venda.
///
/// Cada tela chama só o que ela entende: o início procura comanda e o pedido
/// procura produto. Procurar as duas coisas em toda tela é o que faria um EAN
/// abrir uma ação inesperada — o problema que a separação por tela evita.
class CodeLookupService {
  CodeLookupService(this.gateway);

  final OfflineFirstGateway gateway;

  EntityRepository get _products =>
      gateway.repository(EntityCatalog.product);

  EntityRepository get _commands =>
      gateway.repository(EntityCatalog.command);

  /// A comanda cujo código (ou número) casa com o lido.
  Future<CodeResolution> findCommand(String code) async {
    final match = await _commands.findByCode(code);
    if (match == null) return const CodeResolution.none();
    return CodeResolution.command(match.payload, field: match.field);
  }

  /// O produto cujo código de barras — ou, na falta dele, o código interno —
  /// casa com o lido.
  ///
  /// `restaurantId` e `orderType` recortam o que aquele restaurante de fato
  /// vende naquele tipo de pedido: um produto inativo, de outra unidade ou
  /// indisponível para o balcão não pode entrar no pedido só porque o código
  /// bateu.
  Future<CodeResolution> findProduct(
    String code, {
    String? restaurantId,
    String? orderType,
  }) async {
    final match = await _products.findByCode(code);
    if (match == null) return const CodeResolution.none();
    final product = match.payload;
    if (!isProductSellable(
      product,
      restaurantId: restaurantId,
      orderType: orderType,
    )) {
      return const CodeResolution.none();
    }
    return CodeResolution.product(product, field: match.field);
  }

  /// O produto está ativo e disponível neste restaurante e tipo de pedido?
  static bool isProductSellable(
    Map<String, dynamic> product, {
    String? restaurantId,
    String? orderType,
  }) {
    if (product['is_active'] == false) return false;

    final restaurants = (product['restaurants'] as List? ?? const [])
        .map((item) => '$item')
        .toList();
    // Lista vazia significa "sem recorte" em cadastros antigos; com recorte, o
    // produto precisa estar liberado para a unidade que está vendendo.
    if (restaurantId != null &&
        restaurants.isNotEmpty &&
        !restaurants.contains(restaurantId)) {
      return false;
    }

    return switch (orderType) {
      'table' || 'command' => product['available_for_table'] != false,
      'counter' => product['available_for_counter'] != false,
      'delivery' => product['available_for_delivery'] != false,
      _ => true,
    };
  }
}
