import 'order_presenter.dart';

/// Como a linha do carrinho se LÊ: a quantidade e a lista de escolhas.
///
/// São duas perguntas de formatação — "3" ou "0,750 kg", e "Grande · sem
/// cebola" —, e nenhuma delas precisa do widget para ser respondida. Separadas,
/// dá para conferir as duas sem montar tela nenhuma.
String rotuloDeQuantidade(Map<String, dynamic> item) {
    final label = OrderPresenter.quantityLabel(item);
  return OrderPresenter.isWeighedItem(item) ? '$label ·' : label;
}

/// Variações e adicionais em uma linha, como o frontend web faz.

/// As variações e adicionais escolhidos, em uma linha.
String extrasDoItem(Map<String, dynamic> item) {
  final parts = <String>[
    for (final variation in (item['variations'] as List? ?? const []))
      if (variation is Map)
        '${variation['name'] ?? ''}'.trim()
      else
        '$variation'.trim(),
    for (final addon in (item['addons'] as List? ?? const []))
      if (addon is Map)
        '${addon['addon_name'] ?? addon['name'] ?? ''}'.trim(),
  ];
  return parts.where((part) => part.isNotEmpty).join(' · ');
}
