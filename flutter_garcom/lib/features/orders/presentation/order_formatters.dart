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

/// Como o pedido é chamado no salão: pela mesa, pela comanda ou pelo número.
String orderTitle(Map<String, dynamic> order) {
  final table = '${order['table_number'] ?? ''}'.trim();
  if (table.isNotEmpty && table != 'null') return 'Mesa $table';
  final command = '${order['command_number'] ?? ''}'.trim();
  if (command.isNotEmpty && command != 'null') return 'Comanda $command';
  final customer = '${order['customer_name'] ?? ''}'.trim();
  if (customer.isNotEmpty && customer != 'null') return customer;
  return 'Pedido #${order['sequence'] ?? ''}';
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
