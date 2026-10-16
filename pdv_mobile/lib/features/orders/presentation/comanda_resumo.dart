/// O que a comanda tem, numa linha curta para o cartão da grade:
/// "3x X-Burger · 0,35 kg Picanha · +2".
///
/// Vem pronto do servidor (`pending_preview`, só com `?preview=1` e em
/// `/commands/{id}/items/`): no máximo 4 produtos, o mesmo produto já somado
/// numa linha, cancelado e cortesia de fora. Aqui só se escreve em pt-BR — o
/// quilo com vírgula. Comanda livre (ou resposta sem resumo) devolve vazio.
String resumoDaComanda(Object? preview) {
  if (preview is! Map) return '';
  final itens = preview['items'];
  if (itens is! List || itens.isEmpty) return '';
  final partes = [
    for (final item in itens.whereType<Map>())
      if ('${item['name'] ?? ''}'.trim().isNotEmpty) _parte(item),
  ];
  final mais = int.tryParse('${preview['more'] ?? 0}') ?? 0;
  if (mais > 0) partes.add('+$mais');
  return partes.join(' · ');
}

String _parte(Map item) {
  final nome = '${item['name']}'.trim();
  final quantidade = '${item['quantity'] ?? ''}'.trim();
  return item['unit'] == 'kg'
      ? '${quantidade.replaceAll('.', ',')} kg $nome'
      : '${quantidade}x $nome';
}
