import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Formas de abrir um pedido, iguais às do PDV.
///
/// **Mesa não está aqui de propósito**: o pedido de salão nasce em uma
/// comanda, e a mesa entra depois como vínculo dela (é o cliente que senta na
/// mesa, não o pedido). O próprio backend recusa `order_type: table`.
enum NewOrderKind {
  comanda('Comanda', Icons.receipt_long_outlined, 'Cliente no salão'),
  balcao('Balcão', Icons.storefront_outlined, 'Consumo no local, sem comanda'),
  delivery('Delivery', Icons.delivery_dining_outlined, 'Entrega no endereço'),
  retirada('Retirada', Icons.shopping_bag_outlined, 'Cliente busca no balcão');

  const NewOrderKind(this.label, this.icon, this.description);

  final String label;
  final IconData icon;
  final String description;

  /// Valor aceito pelo campo `order_type` da API.
  String get orderType => switch (this) {
    NewOrderKind.comanda => 'command',
    NewOrderKind.balcao => 'counter',
    NewOrderKind.delivery => 'delivery',
    NewOrderKind.retirada => 'takeaway',
  };
}

Future<NewOrderKind?> showNewOrderSheet(BuildContext context) =>
    showModalBottomSheet<NewOrderKind>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Novo pedido',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
              ),
            ),
            for (final kind in NewOrderKind.values)
              ListTile(
                leading: Container(
                  height: 40,
                  width: 40,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: Theme.of(
                      context,
                    ).colorScheme.primary.withValues(alpha: .12),
                    borderRadius: AppTheme.radius,
                  ),
                  child: Icon(
                    kind.icon,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                ),
                title: Text(
                  kind.label,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                subtitle: Text(kind.description),
                onTap: () => Navigator.of(context).pop(kind),
              ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
