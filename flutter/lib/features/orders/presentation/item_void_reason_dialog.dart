import 'package:flutter/material.dart';

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
  }) async {
    var selectedReason = reasons.first;
    var showDetailsError = false;
    final detailsController = TextEditingController();

    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) {
          final requiresDetails = selectedReason == 'Outro';
          return AlertDialog(
            title: const Text('Remover item'),
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
                child: const Text('Remover item'),
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
