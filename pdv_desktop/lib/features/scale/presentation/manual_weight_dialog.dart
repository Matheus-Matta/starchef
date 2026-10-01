import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_dialog.dart';
import '../../../core/widgets/touch_keypad.dart';

/// Peso digitado pelo operador quando a balança não transmite.
///
/// Devolve `null` quando a pessoa cancela. O valor já sai validado (maior que
/// zero e até 999 kg): quem chama só decide o que fazer com ele.
Future<double?> showManualWeightDialog(BuildContext context) {
  var rawValue = '';
  String? validationMessage;
  return showDialog<double>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (context, setDialogState) {
        void useWeight() {
          final parsed = double.tryParse(rawValue.replaceAll(',', '.'));
          if (parsed == null || parsed <= 0) {
            setDialogState(
              () => validationMessage = 'Informe um peso maior que zero.',
            );
            return;
          }
          if (parsed > 999) {
            setDialogState(
              () => validationMessage = 'O peso informado é muito alto.',
            );
            return;
          }
          Navigator.pop(dialogContext, parsed);
        }

        return AppDialog(
          title: const Row(
            children: [
              Icon(Icons.touch_app_outlined),
              SizedBox(width: 10),
              Text('Peso manual'),
            ],
          ),
          content: SizedBox(
            width: 390,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 20,
                    vertical: 16,
                  ),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainer,
                    borderRadius: AppTheme.radius,
                  ),
                  child: Text(
                    '${rawValue.isEmpty ? '0,000' : rawValue} kg',
                    textAlign: TextAlign.end,
                    style: const TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.w900,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ),
                if (validationMessage != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      validationMessage!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                const SizedBox(height: 14),
                TouchKeypad(
                  allowDecimal: true,
                  onKey: (key) {
                    setDialogState(() {
                      validationMessage = null;
                      rawValue = nextKeypadValue(
                        rawValue,
                        key,
                        allowDecimal: true,
                        maximumLength: 7,
                      );
                    });
                  },
                ),
                TextButton.icon(
                  onPressed: rawValue.isEmpty
                      ? null
                      : () => setDialogState(() {
                          rawValue = '';
                          validationMessage = null;
                        }),
                  icon: const Icon(Icons.clear),
                  label: const Text('Limpar peso'),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: useWeight,
              icon: const Icon(Icons.check),
              label: const Text('Usar peso'),
            ),
          ],
        );
      },
    ),
  );
}
