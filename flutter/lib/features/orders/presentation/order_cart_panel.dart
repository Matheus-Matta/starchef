import 'package:flutter/material.dart';

/// View reutilizável do resumo do pedido atual.
///
/// Não conhece API nem estado global: recebe dados prontos do presenter e
/// devolve as intenções do operador por callbacks.
class OrderCartPanel extends StatelessWidget {
  const OrderCartPanel({
    super.key,
    required this.order,
    required this.table,
    required this.customer,
    required this.items,
    required this.money,
    required this.onVoidItem,
    required this.onFinish,
    required this.onPrint,
    required this.printing,
  });

  final Map<String, dynamic>? order;
  final Map<String, dynamic>? table;
  final Map<String, dynamic>? customer;
  final List<Map<String, dynamic>> items;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onVoidItem;
  final VoidCallback onFinish;
  final VoidCallback onPrint;
  final bool printing;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(left: BorderSide(color: Theme.of(context).dividerColor)),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(18),
            child: Row(
              children: [
                const Icon(Icons.receipt_long),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        order == null
                            ? 'Novo pedido'
                            : 'Pedido #${order!['sequence']}',
                        style: const TextStyle(
                          fontWeight: FontWeight.w800,
                          fontSize: 18,
                        ),
                      ),
                      Text(_contextLabel()),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(child: items.isEmpty ? _empty() : _items()),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Total',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      money(order?['total']),
                      style: const TextStyle(
                        fontSize: 24,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  height: 56,
                  child: FilledButton.icon(
                    onPressed: order != null && items.isNotEmpty
                        ? onFinish
                        : null,
                    icon: const Icon(Icons.check_circle, size: 22),
                    label: const Text(
                      'Finalizar pedido',
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: OutlinedButton.icon(
                    onPressed: order != null && items.isNotEmpty && !printing
                        ? onPrint
                        : null,
                    icon: printing
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.receipt_long_outlined),
                    label: Text(
                      printing ? 'Gerando nota...' : 'Imprimir nota do cliente',
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _contextLabel() {
    if (table != null) return 'Mesa ${table!['number']}';
    if (customer != null) {
      return '${customer!['name']} · ${customer!['phone']}';
    }
    return '${order?['customer_name'] ?? 'Balcão'}';
  }

  Widget _empty() => const Center(
    child: Padding(
      padding: EdgeInsets.all(24),
      child: Text(
        'Selecione uma mesa e adicione produtos.',
        textAlign: TextAlign.center,
      ),
    ),
  );

  Widget _items() => ListView.separated(
    padding: const EdgeInsets.all(14),
    itemCount: items.length,
    separatorBuilder: (_, _) => const Divider(),
    itemBuilder: (_, index) {
      final item = items[index];
      final note = '${item['customer_note'] ?? ''}';
      return ListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(
          '${item['product_name']}',
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          '${item['quantity']} × ${money(item['unit_price'])}'
          '${note.isEmpty ? '' : '\n$note'}',
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              money(item['total_price']),
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            IconButton(
              tooltip: 'Remover item',
              onPressed: item['status'] == 'pending'
                  ? () => onVoidItem(item)
                  : null,
              icon: const Icon(Icons.close),
            ),
          ],
        ),
      );
    },
  );
}
