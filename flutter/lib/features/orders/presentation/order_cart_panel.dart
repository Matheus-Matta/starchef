import 'package:flutter/material.dart';

/// Painel visual do pedido atual.
///
/// Continua sem dependência de API: recebe dados prontos e comunica intenções
/// por callbacks, mantendo as regras transacionais na tela/controlador do PDV.
class OrderCartPanel extends StatelessWidget {
  const OrderCartPanel({
    super.key,
    required this.order,
    required this.table,
    this.command,
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
  final Map<String, dynamic>? command;
  final Map<String, dynamic>? customer;
  final List<Map<String, dynamic>> items;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onVoidItem;
  final VoidCallback onFinish;
  final VoidCallback onPrint;
  final bool printing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(left: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Column(
        children: [
          _header(context),
          Divider(height: 1, color: scheme.outlineVariant),
          Expanded(child: items.isEmpty ? _empty(context) : _items(context)),
          Divider(height: 1, color: scheme.outlineVariant),
          _footer(context),
        ],
      ),
    );
  }

  Widget _header(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pendingOffline = order?['_offline_pending'] == true;
    return Padding(
      padding: const EdgeInsets.fromLTRB(17, 15, 13, 14),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: scheme.primaryContainer,
              borderRadius: BorderRadius.circular(11),
            ),
            child: Icon(
              Icons.receipt_long_outlined,
              color: scheme.primary,
              size: 21,
            ),
          ),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  order == null
                      ? 'Novo pedido'
                      : 'Pedido #${order!['sequence']}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontWeight: FontWeight.w900,
                    fontSize: 16,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  _contextLabel(),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          if (pendingOffline)
            Tooltip(
              message: 'Pedido salvo localmente e aguardando sincronização.',
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                decoration: BoxDecoration(
                  color: scheme.tertiaryContainer,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'LOCAL',
                  style: TextStyle(fontSize: 9, fontWeight: FontWeight.w900),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _footer(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final subtotal = order?['subtotal'];
    final serviceFee = _number(order?['service_fee']);
    final deliveryFee = _number(order?['delivery_fee']);
    final discount = _number(order?['discount']);
    return Padding(
      padding: const EdgeInsets.fromLTRB(17, 13, 17, 16),
      child: Column(
        children: [
          _summaryRow(context, 'Subtotal', money(subtotal ?? order?['total'])),
          if (serviceFee.abs() > .009)
            _summaryRow(context, 'Taxa de serviço', money(serviceFee)),
          if (deliveryFee.abs() > .009)
            _summaryRow(context, 'Taxa de entrega', money(deliveryFee)),
          if (discount.abs() > .009)
            _summaryRow(
              context,
              'Desconto',
              '- ${money(discount.abs())}',
              valueColor: scheme.primary,
            ),
          const SizedBox(height: 7),
          Divider(height: 1, color: scheme.outlineVariant),
          const SizedBox(height: 11),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Total',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
              ),
              Text(
                money(order?['total']),
                style: TextStyle(
                  color: scheme.primary,
                  fontSize: 25,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
          const SizedBox(height: 13),
          SizedBox(
            width: double.infinity,
            height: 54,
            child: FilledButton.icon(
              onPressed: order != null && items.isNotEmpty ? onFinish : null,
              icon: const Icon(Icons.arrow_forward_rounded, size: 21),
              label: const Text(
                'Revisar pedido',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
              ),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            height: 44,
            child: OutlinedButton.icon(
              onPressed: order != null && items.isNotEmpty && !printing
                  ? onPrint
                  : null,
              icon: printing
                  ? const SizedBox(
                      width: 17,
                      height: 17,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.print_outlined, size: 19),
              label: Text(
                printing ? 'Gerando nota...' : 'Imprimir nota do cliente',
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _summaryRow(
    BuildContext context,
    String label,
    String value, {
    Color? valueColor,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: scheme.onSurfaceVariant,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: valueColor,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }

  String _contextLabel() {
    final type = '${order?['order_type'] ?? ''}';
    if (table != null) return 'Mesa ${table!['number']} · Salão';
    if (command != null) {
      final name = '${command!['customer_name'] ?? ''}'.trim();
      final label = 'Comanda ${command!['number']}';
      return name.isEmpty ? '$label · Self-service' : '$label · $name';
    }
    if (customer != null) {
      final phone = '${customer!['phone'] ?? ''}'.trim();
      return phone.isEmpty
          ? '${customer!['name']} · ${_typeLabel(type)}'
          : '${customer!['name']} · $phone';
    }
    final customerName = '${order?['customer_name'] ?? ''}'.trim();
    if (customerName.isNotEmpty) {
      return '$customerName · ${_typeLabel(type)}';
    }
    return _typeLabel(type);
  }

  Widget _empty(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final type = '${order?['order_type'] ?? ''}';
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(28),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 62,
              height: 62,
              decoration: BoxDecoration(
                color: scheme.surfaceContainer,
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.shopping_basket_outlined,
                color: scheme.onSurfaceVariant,
                size: 29,
              ),
            ),
            const SizedBox(height: 13),
            const Text(
              'O pedido está vazio',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 5),
            Text(
              type == 'table'
                  ? 'Toque em um produto para adicioná-lo à mesa.'
                  : 'Toque em um produto do cardápio para começar.',
              textAlign: TextAlign.center,
              style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }

  /// Lista os itens agrupados por situação, como no frontend web.
  ///
  /// Separar o que já foi para a produção do que ainda aguarda envio é a
  /// informação que o operador precisa antes de fechar: só a segunda parte
  /// ainda pode ser removida.
  Widget _items(BuildContext context) {
    final sent = items
        .where((item) => item['status'] != 'pending')
        .toList(growable: false);
    final pending = items
        .where((item) => item['status'] == 'pending')
        .toList(growable: false);

    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      children: [
        if (sent.isNotEmpty) ...[
          _sectionLabel(
            context,
            icon: Icons.soup_kitchen_outlined,
            label: 'Em produção (${sent.length})',
          ),
          for (final item in sent)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _CartItem(
                item: item,
                money: money,
                canRemove: false,
                onRemove: () {},
              ),
            ),
        ],
        if (pending.isNotEmpty) ...[
          _sectionLabel(
            context,
            icon: Icons.schedule_outlined,
            label: 'Aguardando envio (${pending.length})',
            highlight: true,
          ),
          for (final item in pending)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _CartItem(
                item: item,
                money: money,
                canRemove: true,
                onRemove: () => onVoidItem(item),
              ),
            ),
        ],
      ],
    );
  }

  Widget _sectionLabel(
    BuildContext context, {
    required IconData icon,
    required String label,
    bool highlight = false,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final color = highlight ? scheme.primary : scheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 4, 2, 7),
      child: Row(
        children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 6),
          Text(
            label.toUpperCase(),
            style: TextStyle(
              color: color,
              fontSize: 10,
              fontWeight: FontWeight.w900,
              letterSpacing: .5,
            ),
          ),
        ],
      ),
    );
  }

  static String _typeLabel(String type) => switch (type) {
    'table' => 'Salão',
    'delivery' => 'Delivery',
    'takeaway' => 'Retirada',
    'counter' => 'Balcão',
    _ => 'Balcão',
  };

  static double _number(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse('${value ?? ''}'.replaceAll(',', '.')) ?? 0;
  }
}

/// Linha do pedido, no mesmo formato do frontend web.
///
/// Sem miniatura do produto: a foto ocupava espaço numa coluna estreita sem
/// ajudar quem já escolheu o item, e uma imagem remota ainda falhava com o
/// terminal offline. O que importa aqui é nome, variações, observação,
/// quantidade e valor.
class _CartItem extends StatelessWidget {
  const _CartItem({
    required this.item,
    required this.canRemove,
    required this.money,
    required this.onRemove,
  });

  final Map<String, dynamic> item;
  final bool canRemove;
  final String Function(dynamic) money;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = '${item['customer_note'] ?? ''}'.trim();
    final extras = _extras();
    final comped = item['status'] == 'comped';

    return Container(
      padding: const EdgeInsets.fromLTRB(11, 9, 7, 9),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(11),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${item['product_name']}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.2,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (extras.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    extras,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
                if (note.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    note,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 10,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ],
                if (!canRemove) ...[
                  const SizedBox(height: 5),
                  _statusChip(context),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${_quantityLabel()} ${money(item['unit_price'])}'
                '${item['pricing_unit'] == 'kg' ? '/kg' : ''}',
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                money(item['total_price']),
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  decoration: comped ? TextDecoration.lineThrough : null,
                  color: comped ? scheme.onSurfaceVariant : null,
                ),
              ),
            ],
          ),
          if (canRemove)
            SizedBox(
              width: 30,
              height: 30,
              child: IconButton(
                padding: EdgeInsets.zero,
                tooltip: 'Cancelar item',
                onPressed: onRemove,
                icon: const Icon(Icons.close_rounded, size: 17),
              ),
            )
          else
            const SizedBox(width: 30),
        ],
      ),
    );
  }

  Widget _statusChip(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final batch = item['batch_number'];
    return Wrap(
      spacing: 5,
      runSpacing: 4,
      children: [
        if (batch != null)
          _chip(context, 'Rodada $batch', scheme.surfaceContainerHigh),
        _chip(
          context,
          _statusLabel('${item['status'] ?? ''}'),
          scheme.secondaryContainer,
        ),
      ],
    );
  }

  Widget _chip(BuildContext context, String label, Color background) =>
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(5),
        ),
        child: Text(
          label,
          style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w800),
        ),
      );

  String _quantityLabel() {
    final quantity = OrderCartPanel._number(item['quantity']);
    if (item['pricing_unit'] == 'kg') {
      return '${quantity.toStringAsFixed(3).replaceAll('.', ',')} kg ×';
    }
    return '${quantity.toStringAsFixed(0)}×';
  }

  /// Variações e adicionais em uma linha, como o frontend web faz.
  String _extras() {
    final parts = <String>[
      for (final variation in (item['variations'] as List? ?? const []))
        if (variation is Map)
          '${variation['name'] ?? ''}'.trim()
        else
          '$variation'.trim(),
      for (final addon in (item['addons'] as List? ?? const []))
        if (addon is Map) '${addon['addon_name'] ?? addon['name'] ?? ''}'.trim(),
    ];
    return parts.where((part) => part.isNotEmpty).join(' · ');
  }

  static String _statusLabel(String status) => switch (status) {
    'pending' => 'Pendente',
    'sent' => 'Cozinha',
    'preparing' => 'Preparo',
    'ready' => 'Pronto',
    'delivered' => 'Entregue',
    'cancelled' => 'Cancelado',
    'comped' => 'Cortesia',
    _ => status,
  };
}
