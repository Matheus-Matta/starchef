import 'package:flutter/material.dart';

import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

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
      padding: AppTheme.bannerPadding,
      child: Column(
        children: [
          if (pending > 0) _pendingNotice(pending),
          if (failed > 0) ...[
            if (pending > 0) const SizedBox(height: AppTheme.gapTight),
            _failedNotice(failed),
          ],
        ],
      ),
    );
  }

  Widget _pendingNotice(int count) {
    final flushing = gateway.flushing;
    return AppNotice(
      icon: Icons.cloud_off,
      leading: flushing
          ? const SizedBox.square(
              dimension: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : null,
      message: flushing
          ? 'Reenviando ${_plural(count, 'alteração', 'alterações')}...'
          : '${_plural(count, 'alteração salva', 'alterações salvas')} no '
                'aparelho, aguardando o Caixa Principal.',
      actionLabel: flushing ? null : 'Tentar agora',
      onAction: gateway.flushNow,
    );
  }

  Widget _failedNotice(int count) => AppNotice(
    tone: AppNoticeTone.danger,
    icon: Icons.error_outline,
    message:
        '${_plural(count, 'operação recusada', 'operações recusadas')} pelo '
        'caixa. Toque para ver.',
    trailing: const Icon(
      Icons.chevron_right,
      size: 18,
      color: AppColors.danger,
    ),
    onTap: onOpenFailed,
  );

  static String _plural(int count, String one, String many) =>
      '$count ${count == 1 ? one : many}';
}
