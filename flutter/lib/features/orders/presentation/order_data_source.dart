import 'package:flutter/material.dart';

/// Adapta os pedidos da API para a tabela paginada e delega ações à View.
class OrderDataSource extends DataTableSource {
  OrderDataSource(
    this.orders, {
    required this.money,
    required this.onEdit,
    required this.onPay,
    required this.onPrint,
    required this.allowEdit,
    required this.allowPayment,
  });

  final List<Map<String, dynamic>> orders;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onEdit;
  final ValueChanged<Map<String, dynamic>> onPay;
  final ValueChanged<Map<String, dynamic>> onPrint;
  final bool allowEdit;
  final bool allowPayment;

  @override
  DataRow? getRow(int index) {
    if (index >= orders.length) return null;
    final order = orders[index];
    final status = '${order['status']}';
    final canEdit = allowEdit && {'open', 'awaiting_payment'}.contains(status);
    final canPay =
        allowPayment &&
        status == 'awaiting_payment' &&
        '${order['payment_status']}' != 'paid';
    final contextLabel = order['table_number'] != null
        ? 'Mesa ${order['table_number']}'
        : '${order['customer_name'] ?? 'Balcão'}';

    return DataRow.byIndex(
      index: index,
      onSelectChanged: (_) => onEdit(order),
      cells: [
        DataCell(Text('#${order['sequence']}')),
        DataCell(Text(_typeLabel('${order['order_type']}'))),
        DataCell(Text(contextLabel)),
        DataCell(Text(_statusLabel(status))),
        DataCell(Text(_paymentLabel('${order['payment_status']}'))),
        DataCell(
          Text(
            money(order['total']),
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ),
        DataCell(
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!canEdit)
                IconButton(
                  tooltip: 'Visualizar pedido',
                  onPressed: () => onEdit(order),
                  icon: const Icon(Icons.visibility_outlined),
                ),
              if (canEdit)
                IconButton(
                  tooltip: 'Editar pedido e adicionar itens',
                  onPressed: () => onEdit(order),
                  icon: const Icon(Icons.edit_outlined),
                ),
              if (canPay)
                FilledButton.icon(
                  onPressed: () => onPay(order),
                  icon: const Icon(Icons.payments_outlined, size: 18),
                  label: const Text('Pagar'),
                ),
            ],
          ),
        ),
      ],
    );
  }

  static String _statusLabel(String value) =>
      const {
        'open': 'Em aberto',
        'awaiting_payment': 'Aguardando pagamento',
        'paid': 'Pago',
        'cancelled': 'Cancelado',
        'refunded': 'Estornado',
      }[value] ??
      value;

  static String _paymentLabel(String value) =>
      const {
        'pending': 'Pendente',
        'partial': 'Parcial',
        'paid': 'Pago',
        'refunded': 'Estornado',
      }[value] ??
      value;

  static String _typeLabel(String value) =>
      const {
        'table': 'Mesa',
        'counter': 'Balcão',
        'takeaway': 'Retirada',
        'delivery': 'Delivery',
      }[value] ??
      value;

  @override
  int get rowCount => orders.length;

  @override
  bool get isRowCountApproximate => false;

  @override
  int get selectedRowCount => 0;
}
