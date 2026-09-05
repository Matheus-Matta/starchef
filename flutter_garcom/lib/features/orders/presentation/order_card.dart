import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';
import 'order_formatters.dart';
import 'pending_badge.dart';

/// Uma linha da lista de pedidos abertos.
///
/// O selo da direita mostra UM estado por vez, na ordem em que o garçom
/// precisa reagir: primeiro o que o caixa recusou, depois o que ele escolheu e
/// ainda não mandou, depois o pedido inteiro esperando conexão e, por último,
/// o andamento normal na cozinha.
class OrderCard extends StatelessWidget {
  const OrderCard({
    super.key,
    required this.order,
    required this.onTap,
    this.failed = 0,
    this.draft = 0,
  });

  final Map<String, dynamic> order;

  /// Itens que o Caixa Principal recusou neste pedido.
  final int failed;

  /// Itens escolhidos e ainda não enviados neste pedido.
  final int draft;

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final items = (order['items'] as List? ?? const []).length;
    return InkWell(
      onTap: onTap,
      borderRadius: AppTheme.radius,
      child: ShadCard(
        radius: AppTheme.radius,
        columnCrossAxisAlignment: CrossAxisAlignment.stretch,
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    orderTitle(order),
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    orderSubtitle(order),
                    style: TextStyle(
                      fontSize: 12,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '$items ${items == 1 ? 'item' : 'itens'} · '
                    '${money(order['total'])}',
                    style: TextStyle(
                      fontSize: 13,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            _badge(),
            const SizedBox(width: AppTheme.gapTight),
            Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }

  Widget _badge() {
    if (failed > 0) {
      return AppStatusBadge(
        label: '$failed',
        icon: Icons.error_outline,
        color: AppColors.danger,
      );
    }
    if (draft > 0) {
      return AppStatusBadge(
        label: '$draft',
        icon: Icons.schedule_outlined,
        color: AppColors.warning,
      );
    }
    if (order['_offline_pending'] == true) return const PendingBadge();
    final pending = pendingItems(order);
    return AppStatusBadge(
      label: pending > 0 ? '$pending a enviar' : 'Na cozinha',
      color: pending > 0 ? AppColors.warning : AppColors.success,
    );
  }
}
