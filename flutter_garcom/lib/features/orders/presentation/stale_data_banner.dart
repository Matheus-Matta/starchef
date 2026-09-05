import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../data/orders_repository.dart';

/// Aviso de que a tela está mostrando um retrato, não a verdade de agora.
///
/// Aparece quando o Caixa Principal não respondeu e a leitura saiu da cópia
/// local. É o aviso que impede o erro mais caro do modo offline: lançar um
/// item sobre um pedido que outro terminal já fechou.
class StaleDataBanner extends StatelessWidget {
  const StaleDataBanner({super.key, required this.origin, this.onRetry});

  final ReadOrigin origin;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    if (!origin.fromCache) return const SizedBox.shrink();
    final at = origin.at;
    return Padding(
      padding: AppTheme.bannerPadding,
      child: AppNotice(
        // Dado velho o bastante para o repositório marcar como vencido deixa
        // de ser um aviso e vira risco: a cor acompanha.
        tone: origin.stale ? AppNoticeTone.danger : AppNoticeTone.warning,
        icon: Icons.cloud_off_outlined,
        message: at == null
            ? 'Caixa Principal fora do ar. Mostrando os últimos dados '
                  'recebidos.'
            : 'Caixa Principal fora do ar. Dados de ${_clock(at)} — pode ter '
                  'mudado.',
        actionLabel: onRetry == null ? null : 'Tentar',
        onAction: onRetry,
      ),
    );
  }

  static String _clock(DateTime value) {
    final local = value.toLocal();
    String two(int number) => number.toString().padLeft(2, '0');
    return '${two(local.hour)}:${two(local.minute)}';
  }
}
