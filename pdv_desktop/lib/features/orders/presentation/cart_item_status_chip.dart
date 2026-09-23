import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';

/// O selo de estado da linha do carrinho: "na cozinha", "pronto", "cancelado".
///
/// Sai do card porque é a REGRA DE COR da produção, e regra de cor é o que
/// mais muda depois — quem for ajustar um matiz abre este arquivo e não
/// precisa ler o cartão inteiro.
class CartItemStatusChip extends StatelessWidget {
  const CartItemStatusChip({
    super.key,
    required this.status,
    this.batchNumber,
  });

  final String status;

  /// A rodada em que o item foi para a produção, quando já foi.
  final Object? batchNumber;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final batch = batchNumber;
    return Wrap(
      spacing: 5,
      runSpacing: 4,
      children: [
        if (batch != null)
          _chip(context, 'Rodada $batch', scheme.surfaceContainerHigh),
        _chip(
          context,
          _rotulo(status),
          scheme.secondaryContainer,
        ),
      ],
    );
  }

  Widget _chip(BuildContext context, String label, Color background) =>
      ShadBadge.raw(
        variant: ShadBadgeVariant.secondary,
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        backgroundColor: background,
        foregroundColor: Theme.of(context).colorScheme.onSurface,
        shape: const RoundedRectangleBorder(borderRadius: AppTheme.radius),
        child: Text(
          label,
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800),
        ),
      );

  /// A mesma regra da comanda e do recibo — ver `OrderPresenter.quantityLabel`.
  ///
  /// Peso usa um separador neutro: nunca parece quantidade de peças.

  static String _rotulo(String status) => switch (status) {
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
