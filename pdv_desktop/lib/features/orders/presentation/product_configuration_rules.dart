/// Diz se o produto precisa perguntar algo antes de entrar no consumo.
bool productNeedsConfiguration(Map<String, dynamic> product) =>
    isProductSoldByWeight(product) ||
    product['requires_variation'] == true ||
    _hasActive(product['variations'] as List?) ||
    _hasActive(product['addons'] as List?);

/// Aceita o contrato atual e payloads antigos ainda guardados no terminal.
bool isProductSoldByWeight(Map<String, dynamic> product) =>
    '${product['pricing_unit'] ?? ''}'.toLowerCase() == 'kg' ||
    product['is_weighed'] == true;

bool _hasActive(List? entries) => (entries ?? const []).whereType<Map>().any(
  (entry) => entry['is_active'] != false,
);
