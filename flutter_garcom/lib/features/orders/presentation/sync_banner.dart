import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';

/// Faixa que avisa sobre pendências: o que está esperando a conexão voltar, e
/// o que o caixa recusou de vez.
///
/// Fica embutida em cima da lista (não num diálogo) porque é um estado
/// contínuo do aparelho, não um evento pontual — o garçom precisa ver que
/// ainda há algo pendente sem precisar procurar.
class SyncBanner extends StatelessWidget {
  const SyncBanner({super.key, required this.gateway, this.onOpenFailed});

  final RelayGateway gateway;
  final VoidCallback? onOpenFailed;

  @override
  Widget build(BuildContext context) {
    final pending = gateway.pendingCount;
    final failed = gateway.failed.length;
    if (pending == 0 && failed == 0) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Column(
        children: [
          if (pending > 0) _PendingRow(count: pending, gateway: gateway),
          if (failed > 0) ...[
            if (pending > 0) const SizedBox(height: 8),
            _FailedRow(count: failed, onTap: onOpenFailed),
          ],
        ],
      ),
    );
  }
}

class _PendingRow extends StatelessWidget {
  const _PendingRow({required this.count, required this.gateway});

  final int count;
  final RelayGateway gateway;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
    decoration: BoxDecoration(
      color: AppColors.warning.withValues(alpha: .12),
      borderRadius: AppTheme.radius,
      border: Border.all(color: AppColors.warning.withValues(alpha: .35)),
    ),
    child: Row(
      children: [
        gateway.flushing
            ? const SizedBox.square(
                dimension: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.cloud_off, size: 18, color: AppColors.warning),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            gateway.flushing
                ? 'Reenviando $count alteração${count == 1 ? '' : 'ões'}...'
                : '$count alteração${count == 1 ? '' : 'ões'} salva'
                      '${count == 1 ? '' : 's'} no aparelho, aguardando o '
                      'Caixa Principal.',
            style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
          ),
        ),
        if (!gateway.flushing)
          TextButton(
            onPressed: gateway.flushNow,
            style: TextButton.styleFrom(
              minimumSize: Size.zero,
              padding: const EdgeInsets.symmetric(horizontal: 8),
            ),
            child: const Text('Tentar agora', style: TextStyle(fontSize: 12.5)),
          ),
      ],
    ),
  );
}

class _FailedRow extends StatelessWidget {
  const _FailedRow({required this.count, this.onTap});

  final int count;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => InkWell(
    onTap: onTap,
    borderRadius: AppTheme.radius,
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.danger.withValues(alpha: .1),
        borderRadius: AppTheme.radius,
        border: Border.all(color: AppColors.danger.withValues(alpha: .35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, size: 18, color: AppColors.danger),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              '$count operação${count == 1 ? '' : 'ões'} recusada'
              '${count == 1 ? '' : 's'} pelo caixa. Toque para ver.',
              style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
            ),
          ),
          const Icon(Icons.chevron_right, size: 18, color: AppColors.danger),
        ],
      ),
    ),
  );
}

/// Lista as pendências recusadas — cada uma com o motivo e a opção de
/// descartar (não há reenvio automático: repetir uma recusa de negócio
/// devolveria o mesmo erro).
Future<void> showFailedMutationsSheet(
  BuildContext context,
  RelayGateway gateway,
) => showModalBottomSheet<void>(
  context: context,
  showDragHandle: true,
  isScrollControlled: true,
  builder: (context) => AnimatedBuilder(
    animation: gateway,
    builder: (context, _) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * .7,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(20, 0, 20, 12),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Operações recusadas',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
              ),
            ),
            if (gateway.failed.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text('Nada pendente.'),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                  itemCount: gateway.failed.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, index) {
                    final item = gateway.failed[index];
                    return ShadCard(
                      radius: AppTheme.radius,
                      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  item.mutation.summary,
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  item.reason,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    color: AppColors.danger,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          TextButton(
                            onPressed: () =>
                                gateway.discardFailed(item.mutation.operationId),
                            child: const Text('Descartar'),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    ),
  ),
);

/// Badge compacto para uma pendência dentro do pedido (ver
/// [OrderDetailPage]) — item ainda não lançado, cancelamento ainda não
/// confirmado, envio à cozinha ainda não recebido.
class PendingBadge extends StatelessWidget {
  const PendingBadge({super.key, this.label = 'aguardando conexão'});

  final String label;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
    decoration: BoxDecoration(
      color: AppColors.warning.withValues(alpha: .12),
      borderRadius: AppTheme.radius,
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        const SizedBox.square(
          dimension: 10,
          child: CircularProgressIndicator(strokeWidth: 1.6),
        ),
        const SizedBox(width: 5),
        Text(
          label,
          style: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            color: AppColors.warning,
          ),
        ),
      ],
    ),
  );
}
