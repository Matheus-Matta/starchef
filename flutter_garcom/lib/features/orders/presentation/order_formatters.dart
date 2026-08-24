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
String money(Object? value) => 'R\$ ${amount(value).toStringAsFixed(2).replaceAll('.', ',')}';

/// Como o pedido é chamado no salão.
///
/// A comanda vem antes da mesa: é ela que identifica o atendimento — a mesa é
/// um vínculo que pode mudar durante a refeição, ou nem existir.
String orderTitle(Map<String, dynamic> order) {
  final command = _text(order['command_number']);
  if (command.isNotEmpty) return 'Comanda $command';
  final table = _text(order['table_number']);
  if (table.isNotEmpty) return 'Mesa $table';
  final customer = _text(order['customer_name']);
  if (customer.isNotEmpty) return customer;
  return '${orderTypeLabel(order['order_type'])} #${order['sequence'] ?? ''}';
}

/// Linha de apoio do cartão: tipo do pedido e onde ele está.
String orderSubtitle(Map<String, dynamic> order) {
  final partes = <String>[orderTypeLabel(order['order_type'])];
  final table = _text(order['table_number']);
  if (table.isNotEmpty && _text(order['command_number']).isNotEmpty) {
    partes.add('mesa $table');
  }
  final customer = _text(order['customer_name']);
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

String _text(Object? value) {
  final text = '${value ?? ''}'.trim();
  return text == 'null' ? '' : text;
}

/// Itens ainda não enviados para a cozinha.
///
/// É o número que decide se o botão "Enviar para a cozinha" tem o que fazer:
/// sem itens pendentes, mandar de novo só geraria impressão repetida.
int pendingItems(Map<String, dynamic> order) => orderItems(
  order,
).where((item) => item['status'] == 'pending').length;

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
  'sent' => 'Na cozinha',
  'preparing' => 'Preparando',
  'ready' => 'Pronto',
  'delivered' => 'Entregue',
  _ => '$status',
};
