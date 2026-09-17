import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

/// Selo de uma pendência dentro do pedido — item ainda não lançado,
/// cancelamento ainda não confirmado, envio à cozinha ainda não recebido.
///
/// O progresso circular no lugar do ícone é de propósito: ele diz que alguém
/// ainda está tentando, e que não há nada para o garçom fazer além de esperar.
class PendingBadge extends StatelessWidget {
  const PendingBadge({super.key, this.label = 'aguardando conexão'});

  final String label;

  @override
  Widget build(BuildContext context) => AppStatusBadge(
    label: label,
    color: AppColors.warning,
    leading: const SizedBox.square(
      dimension: 10,
      child: CircularProgressIndicator(strokeWidth: 1.6),
    ),
  );
}
