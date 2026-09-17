import '../network/api_client.dart';
import '../network/api_exception.dart';

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
/// Quem responde é o servidor — o mesmo cadastro que a retaguarda edita. Um
/// produto criado há dez segundos na web já é vendável no bipe seguinte, sem
/// esperar sincronização nenhuma.
///
/// Cada tela chama só o que ela entende: o início procura comanda e o pedido
/// procura produto. Procurar as duas coisas em toda tela é o que faria um EAN
/// abrir uma ação inesperada — o problema que a separação por tela evita.
class CodeLookupService {
  CodeLookupService(this.api, {this.accessToken});

  final ApiClient api;
  final String? accessToken;

  /// A comanda cujo código (ou número) casa com o lido.
  Future<CodeResolution> findCommand(String code) async {
    final normalized = code.trim();
    if (normalized.isEmpty) return const CodeResolution.none();

    // A rota dedicada casa o código impresso na etiqueta — o caso comum do
    // leitor. Um 404 aqui não é erro: é "esta etiqueta não é uma comanda".
    try {
      final response = await api.get(
        '/commands/by-code/',
        query: {'code': normalized},
        accessToken: accessToken,
      );
      if (response['id'] != null) {
        return CodeResolution.command(response, field: 'code');
      }
    } on ApiException catch (error) {
      if (error.isConnectivity) rethrow;
      if (error.statusCode != 404) rethrow;
    }

    // Ninguém digita o código de barras; digita-se o NÚMERO da comanda. Esta
    // segunda volta é o que faz "12" no teclado achar a comanda 12.
    final search = await api.get(
      '/commands/',
      query: {'search': normalized, 'page_size': 25},
      accessToken: accessToken,
    );
    for (final raw in (search['results'] as List? ?? const [])) {
      if (raw is! Map) continue;
      final command = Map<String, dynamic>.from(raw);
      for (final field in const ['code', 'number']) {
        if ('${command[field] ?? ''}'.trim() == normalized) {
          return CodeResolution.command(command, field: field);
        }
      }
    }
    return const CodeResolution.none();
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
    final normalized = code.trim();
    if (normalized.isEmpty) return const CodeResolution.none();

    final response = await api.get(
      '/menu/products/',
      query: {
        'search': normalized,
        'page_size': 25,
        'restaurant': ?restaurantId,
      },
      accessToken: accessToken,
    );
    final results = (response['results'] as List? ?? const [])
        .whereType<Map>()
        .map((raw) => Map<String, dynamic>.from(raw))
        .toList();

    // A busca do servidor também casa NOME e descrição. Um código lido precisa
    // bater exatamente no campo certo: sem este filtro, bipar "500" venderia o
    // primeiro produto cujo nome tem "500" no meio.
    for (final field in const ['ean', 'internal_code']) {
      for (final product in results) {
        if ('${product[field] ?? ''}'.trim() != normalized) continue;
        if (!isProductSellable(
          product,
          restaurantId: restaurantId,
          orderType: orderType,
        )) {
          continue;
        }
        return CodeResolution.product(product, field: field);
      }
    }
    return const CodeResolution.none();
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
