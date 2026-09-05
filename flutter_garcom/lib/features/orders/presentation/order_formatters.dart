/// Formatação e leitura dos campos de pedido devolvidos pela API.
///
/// A API devolve decimais como texto ("12.50") para não perder precisão em
/// ponto flutuante — por isso tudo aqui passa por [amount] antes de virar
/// número.
double amount(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse('${value ?? ''}'.replaceAll(',', '.')) ?? 0;
}

/// Valor em reais, no formato que o garçom lê na comanda.
String money(Object? value) =>
    'R\$ ${amount(value).toStringAsFixed(2).replaceAll('.', ',')}';

/// Preço de uma unidade do produto com a variação e os adicionais escolhidos:
/// base + delta da variação (se houver) + soma dos adicionais marcados.
///
/// Mesma fórmula do PDV desktop (`OrderPresenter.expectedUnitPrice`) — é só
/// uma prévia para o garçom conferir antes de lançar; quem cobra de verdade é
/// o backend, na hora de gravar o item.
double expectedUnitPrice(
  Map<String, dynamic> product, {
  String? variationId,
  Iterable<String> addonIds = const [],
}) {
  var total = amount(product['sale_price']);
  for (final variation in (product['variations'] as List? ?? const [])) {
    if (variation is Map && '${variation['id']}' == variationId) {
      total += amount(variation['price_delta']);
    }
  }
  final addonSet = addonIds.toSet();
  for (final addon in (product['addons'] as List? ?? const [])) {
    if (addon is Map && addonSet.contains('${addon['id']}')) {
      total += amount(addon['price']);
    }
  }
  return total;
}

/// Como o pedido é chamado no salão.
///
/// A comanda vem antes da mesa: é ela que identifica o atendimento — a mesa é
/// um vínculo que pode mudar durante a refeição, ou nem existir.
String orderTitle(Map<String, dynamic> order) {
  final command = fieldText(order['command_number']);
  if (command.isNotEmpty) return 'Comanda $command';
  final table = fieldText(order['table_number']);
  if (table.isNotEmpty) return 'Mesa $table';
  final customer = fieldText(order['customer_name']);
  if (customer.isNotEmpty) return customer;
  return '${orderTypeLabel(order['order_type'])} #${order['sequence'] ?? ''}';
}

/// Linha de apoio do cartão: tipo do pedido e onde ele está.
String orderSubtitle(Map<String, dynamic> order) {
  final partes = <String>[orderTypeLabel(order['order_type'])];
  final table = fieldText(order['table_number']);
  if (table.isNotEmpty && fieldText(order['command_number']).isNotEmpty) {
    partes.add('mesa $table');
  }
  final customer = fieldText(order['customer_name']);
  if (customer.isNotEmpty) partes.add(customer);
  return partes.join(' · ');
}

/// Nome dos tipos de pedido, iguais aos do PDV. `table` não está aqui: o
/// backend recusa esse tipo — pedido de salão nasce em comanda.
String orderTypeLabel(Object? type) => switch ('$type') {
  'command' => 'Comanda',
  'counter' => 'Balcão',
  'delivery' => 'Delivery',
  'takeaway' => 'Retirada',
  'internal' => 'Interno',
  _ => 'Pedido',
};

/// Texto de um campo da API, já limpo.
///
/// A API devolve ausência de três formas diferentes — campo faltando, `null`
/// de verdade e a string `"null"` vinda da interpolação de um id vazio. As
/// três viram string vazia aqui, para nenhuma tela precisar repetir o
/// `.trim() != 'null'` que estava espalhado.
String fieldText(Object? value) {
  final text = '${value ?? ''}'.trim();
  return text == 'null' ? '' : text;
}

/// Itens ainda não enviados para a cozinha.
///
/// É o número que decide se o botão "Enviar para a cozinha" tem o que fazer:
/// sem itens pendentes, mandar de novo só geraria impressão repetida.
int pendingItems(Map<String, dynamic> order) =>
    orderItems(order).where((item) => item['status'] == 'pending').length;

List<Map<String, dynamic>> orderItems(Map<String, dynamic> order) {
  final items = order['items'];
  if (items is List) {
    return items
        .whereType<Map>()
        .map(Map<String, dynamic>.from)
        .where((item) => item['status'] != 'cancelled')
        .toList(growable: false);
  }
  return const [];
}

/// Rótulo do estado do item na cozinha.
String itemStatusLabel(Object? status) => switch ('$status') {
  'pending' => 'A enviar',
  'queued' => 'Enviando para produção',
  'sent' => 'Na cozinha',
  'preparing' => 'Preparando',
  'ready' => 'Pronto',
  'delivered' => 'Entregue',
  _ => '$status',
};
