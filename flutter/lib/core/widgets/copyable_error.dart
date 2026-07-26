import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

Future<void> copyError(BuildContext context, String message) async {
  await Clipboard.setData(ClipboardData(text: message));
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(
      content: Text('Erro copiado para a área de transferência.'),
      duration: Duration(milliseconds: 1500),
    ),
  );
}

void showCopyableError(BuildContext context, String message) {
  final messenger = ScaffoldMessenger.of(context);
  messenger.hideCurrentSnackBar();
  messenger.showSnackBar(
    SnackBar(
      content: Text(message, maxLines: 3, overflow: TextOverflow.ellipsis),
      backgroundColor: Theme.of(context).colorScheme.error,
      duration: const Duration(milliseconds: 1500),
      action: SnackBarAction(
        label: 'COPIAR',
        textColor: Theme.of(context).colorScheme.onError,
        onPressed: () => copyError(context, message),
      ),
    ),
  );
}
