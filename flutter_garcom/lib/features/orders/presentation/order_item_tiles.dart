import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/pending_mutation.dart';
import '../../../core/theme/app_theme.dart';
import '../data/order_drafts.dart';
import 'order_formatters.dart';
import 'pending_badge.dart';

/// As quatro linhas possíveis de um pedido, na ordem em que o garçom pensa:
/// o que já está na cozinha, o que ele acabou de escolher, o que está a
/// caminho do caixa e o que o caixa recusou.
///
/// Todas usam a mesma moldura ([_Tile]) — o que muda é o quadradinho da
/// esquerda, o texto e o que dá para fazer na direita. Antes eram quatro
/// `Container`/`ShadCard` escritos separadamente, e cada um tinha um respiro
/// e um tamanho de marcador ligeiramente diferentes.

/// Item já lançado no pedido.
class OrderItemTile extends StatelessWidget {
  const OrderItemTile({
    super.key,
    required this.item,
    this.onVoid,
    this.voiding = false,
  });

  final Map<String, dynamic> item;
  final VoidCallback? onVoid;

  /// O cancelamento foi pedido e o caixa ainda não confirmou.
  final bool voiding;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = fieldText(item['customer_note']);
    final cancellable = !{'cancelled', 'comped'}.contains('${item['status']}');
    return _Tile(
      marker: _Marker(
        color: scheme.primary,
        child: Text(
          '${amount(item['quantity']).toStringAsFixed(0)}x',
          style: TextStyle(fontWeight: FontWeight.w700, color: scheme.primary),
        ),
      ),
      title: '${item['product_name'] ?? 'Item'}',
      subtitle:
          '${itemStatusLabel(item['status'])} · ${money(item['total_price'])}',
      badge: voiding ? const PendingBadge(label: 'cancelando...') : null,
      note: note,
      trailing: cancellable && !voiding && onVoid != null
          ? IconButton(
              tooltip: item['status'] == 'queued'
                  ? 'Cancelar antes da impressão'
                  : 'Cancelar item',
              onPressed: onVoid,
              icon: Icon(Icons.close, color: scheme.error, size: 20),
            )
          : null,
    );
  }
}

/// Item escolhido e ainda não enviado — só existe neste aparelho.
class DraftItemTile extends StatelessWidget {
  const DraftItemTile({super.key, required this.item, this.onRemove});

  final DraftItem item;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) => _Tile(
    borderColor: AppColors.warning.withValues(alpha: .45),
    marker: const _Marker(
      color: AppColors.warning,
      child: Icon(Icons.edit_note, size: 18, color: AppColors.warning),
    ),
    title: item.label,
    subtitle: 'Ainda não enviado',
    subtitleColor: AppColors.warning,
    note: item.note,
    trailing: IconButton(
      tooltip: 'Remover',
      onPressed: onRemove,
      icon: const Icon(Icons.close),
    ),
  );
}

/// Item lançado sem conexão: ainda não existe no pedido de verdade, só na fila
/// do aparelho. Some sozinho assim que o Caixa Principal confirma — o pedido é
/// recarregado e essa linha vira um item de verdade.
class QueuedItemTile extends StatelessWidget {
  const QueuedItemTile({super.key, required this.mutation});

  final PendingMutation mutation;

  @override
  Widget build(BuildContext context) => _Tile(
    marker: const _Marker(
      color: AppColors.warning,
      child: Icon(Icons.hourglass_empty, size: 16, color: AppColors.warning),
    ),
    title: mutation.summary,
    badge: const PendingBadge(),
  );
}

/// Item que o Caixa Principal recusou — com o motivo e o que fazer.
class FailedItemTile extends StatelessWidget {
  const FailedItemTile({
    super.key,
    required this.failure,
    this.onRetry,
    this.onDiscard,
  });

  final FailedMutation failure;
  final VoidCallback? onRetry;
  final VoidCallback? onDiscard;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.danger.withValues(alpha: .06),
        borderRadius: AppTheme.radius,
        border: Border.all(color: AppColors.danger.withValues(alpha: .45)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            failure.mutation.summary,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(
            failure.reason,
            style: const TextStyle(fontSize: 12, color: AppColors.danger),
          ),
          const SizedBox(height: AppTheme.gapTight),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              TextButton.icon(
                onPressed: onDiscard,
                icon: const Icon(Icons.delete_outline, size: 18),
                label: const Text('Remover'),
                style: TextButton.styleFrom(
                  foregroundColor: scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(width: 4),
              FilledButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('Reenviar'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Moldura comum das linhas de item.
class _Tile extends StatelessWidget {
  const _Tile({
    required this.marker,
    required this.title,
    this.subtitle,
    this.subtitleColor,
    this.note = '',
    this.badge,
    this.trailing,
    this.borderColor,
  });

  final Widget marker;
  final String title;
  final String? subtitle;
  final Color? subtitleColor;
  final String note;
  final Widget? badge;
  final Widget? trailing;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ShadCard(
      radius: AppTheme.radius,
      border: borderColor == null
          ? null
          : ShadBorder.all(color: borderColor, radius: AppTheme.radius),
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          marker,
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                if (subtitle != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    subtitle!,
                    style: TextStyle(
                      fontSize: 12,
                      color: subtitleColor ?? scheme.onSurfaceVariant,
                    ),
                  ),
                ],
                if (note.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    note,
                    style: TextStyle(
                      fontSize: 12,
                      fontStyle: FontStyle.italic,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
                if (badge != null) ...[
                  const SizedBox(height: AppTheme.gapTight),
                  Align(alignment: Alignment.centerLeft, child: badge!),
                ],
              ],
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// O quadradinho da esquerda: quantidade, ampulheta ou lápis.
class _Marker extends StatelessWidget {
  const _Marker({required this.color, required this.child});

  final Color color;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    width: 34,
    height: 34,
    alignment: Alignment.center,
    decoration: BoxDecoration(
      color: color.withValues(alpha: .12),
      borderRadius: AppTheme.radius,
    ),
    child: child,
  );
}
