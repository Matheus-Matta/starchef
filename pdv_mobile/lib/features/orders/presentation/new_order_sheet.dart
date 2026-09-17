import 'package:flutter/material.dart';

import '../../../core/widgets/app_sheet.dart';

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
    showAppSheet<NewOrderKind>(
      context,
      builder: (context) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const AppSheetHeader(title: 'Novo pedido'),
          for (final kind in NewOrderKind.values)
            AppSheetOption(
              icon: kind.icon,
              label: kind.label,
              description: kind.description,
              onTap: () => Navigator.of(context).pop(kind),
            ),
          const SizedBox(height: 12),
        ],
      ),
    );
