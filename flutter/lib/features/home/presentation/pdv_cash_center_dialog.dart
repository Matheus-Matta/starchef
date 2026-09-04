import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_dialog.dart';
import '../../../core/widgets/shadcn_layout.dart';

class PdvCashCenterDialog extends StatelessWidget {
  const PdvCashCenterDialog({
    super.key,
    required this.cashSession,
    required this.balanceLabel,
  });

  final Map<String, dynamic>? cashSession;
  final String balanceLabel;

  static Future<String?> show(
    BuildContext context, {
    required Map<String, dynamic>? cashSession,
    required String balanceLabel,
  }) => showDialog<String>(
    context: context,
    builder: (_) => PdvCashCenterDialog(
      cashSession: cashSession,
      balanceLabel: balanceLabel,
    ),
  );

  void _select(BuildContext context, String value) =>
      Navigator.of(context).pop(value);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final opened = cashSession != null;
    return AppDialog(
      scrollable: true,
      maxWidth: 528,
      title: const Row(
        children: [
          Icon(Icons.account_balance_wallet_outlined),
          SizedBox(width: 10),
          Expanded(child: Text('Financeiro do caixa')),
        ],
      ),
      content: SizedBox(
        width: 480,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: scheme.surfaceContainer,
                borderRadius: AppTheme.radius,
                border: Border.all(color: scheme.outlineVariant),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    opened ? 'Caixa aberto' : 'Caixa fechado',
                    style: TextStyle(
                      color: opened ? const Color(0xFF167A3E) : scheme.error,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    opened
                        ? balanceLabel
                        : 'Abra uma sessão para iniciar as vendas.',
                    style: TextStyle(
                      fontSize: opened ? 30 : 16,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  if (opened)
                    Text(
                      '${cashSession!['station'] ?? 'Estação atual'}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(color: scheme.onSurfaceVariant),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            if (!opened)
              FilledButton.icon(
                onPressed: () => _select(context, 'open'),
                icon: const Icon(Icons.lock_open),
                label: const Text('Abrir caixa'),
              )
            else
              AppResponsiveFields(
                breakpoint: 420,
                spacing: 10,
                children: [
                  OutlinedButton.icon(
                    onPressed: () => _select(context, 'supply'),
                    icon: const Icon(Icons.add_circle_outline),
                    label: const Text('Suprimento'),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => _select(context, 'withdrawal'),
                    icon: const Icon(Icons.remove_circle_outline),
                    label: const Text('Sangria'),
                  ),
                ],
              ),
          ],
        ),
      ),
      actions: [
        if (opened)
          TextButton.icon(
            onPressed: () => _select(context, 'close'),
            icon: const Icon(Icons.lock_outline),
            label: const Text('Fechar caixa'),
          ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Voltar'),
        ),
      ],
    );
  }
}
