import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

/// Solicita um motivo objetivo antes de cancelar um item do pedido.
class ItemVoidReasonDialog {
  static const reasons = [
    'Lançamento incorreto',
    'Cliente desistiu',
    'Item duplicado',
    'Produto indisponível',
    'Troca solicitada',
    'Outro',
  ];

  static Future<String?> show(
    BuildContext context, {
    required String itemName,
    String title = 'Remover item',
    String confirmLabel = 'Remover item',

    /// Consequência que o operador precisa saber ANTES de confirmar (ex.: que
    /// vai sair um cupom de cancelamento na cozinha). Fica em destaque, não
    /// como texto solto no meio do formulário.
    String? warning,
  }) async {
    var selectedReason = reasons.first;
    var showDetailsError = false;
    final detailsController = TextEditingController();

    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) {
          final requiresDetails = selectedReason == 'Outro';
          return AppDialog(
            scrollable: true,
            maxWidth: 488,
            title: Text(title),
            content: SizedBox(
              width: 440,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    itemName,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  if (warning != null) ...[
                    const SizedBox(height: 14),
                    _WarningBanner(message: warning),
                  ],
                  const SizedBox(height: 16),
                  const Text('Selecione o motivo do cancelamento:'),
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: reasons
                        .map(
                          (reason) => ChoiceChip(
                            label: Text(reason),
                            selected: selectedReason == reason,
                            onSelected: (_) => setDialogState(() {
                              selectedReason = reason;
                              showDetailsError = false;
                            }),
                          ),
                        )
                        .toList(),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: detailsController,
                    autofocus: false,
                    maxLength: 180,
                    maxLines: 2,
                    decoration: InputDecoration(
                      labelText: requiresDetails
                          ? 'Descreva o motivo'
                          : 'Observação complementar (opcional)',
                      hintText: 'Ex.: cliente pediu a troca do sabor',
                      errorText: showDetailsError
                          ? 'Informe o motivo do cancelamento.'
                          : null,
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Voltar'),
              ),
              FilledButton(
                onPressed: () {
                  final details = detailsController.text.trim();
                  if (requiresDetails && details.isEmpty) {
                    setDialogState(() => showDetailsError = true);
                    return;
                  }
                  final reason = details.isEmpty
                      ? selectedReason
                      : '$selectedReason — $details';
                  Navigator.pop(dialogContext, reason);
                },
                child: Text(confirmLabel),
              ),
            ],
          );
        },
      ),
    );
    detailsController.dispose();
    return result;
  }
}

class _WarningBanner extends StatelessWidget {
  const _WarningBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: scheme.errorContainer.withValues(alpha: .5),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.error.withValues(alpha: .4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.print_outlined, size: 18, color: scheme.error),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: scheme.onErrorContainer,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
