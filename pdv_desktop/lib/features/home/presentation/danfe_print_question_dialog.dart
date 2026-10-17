import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// A nota está a caminho da autorização e vale esperar por ela?
///
/// Recusa e erro de configuração pedem correção humana; documento local
/// ainda na fila (id `offline-…`) nem existe no servidor para ser consultado.
/// É também o que decide se a pergunta do DANFE aparece: nota que não vai
/// ser autorizada não tem o que imprimir.
bool danfeOnTheWay(Map<String, dynamic> invoice) {
  final invoiceId = '${invoice['id'] ?? ''}';
  const inFlight = {'processing', 'awaiting_transmission'};
  return invoiceId.isNotEmpty &&
      !invoiceId.startsWith('offline-') &&
      inFlight.contains('${invoice['fiscal_state'] ?? ''}');
}

/// "Imprimir a NFC-e?" — a pergunta do restaurante com `ask_print_danfe`.
///
/// Feita para teclado: Enter imprime, Esc cancela. Clicar em Cancelar ou fora
/// do modal também cancela. A nota já foi (ou está sendo) emitida de qualquer
/// jeito; a resposta decide só o papel.
class DanfePrintQuestionDialog extends StatelessWidget {
  const DanfePrintQuestionDialog({super.key, required this.summary});

  final String summary;

  /// Mostra a pergunta e devolve `true` só quando o operador mandou imprimir.
  /// Fechar de qualquer outro jeito (Esc, fora do modal) conta como não.
  static Future<bool> ask(
    BuildContext context, {
    required String summary,
  }) async {
    final answer = await showDialog<bool>(
      context: context,
      barrierDismissible: true,
      builder: (_) => DanfePrintQuestionDialog(summary: summary),
    );
    return answer == true;
  }

  KeyEventResult _key(BuildContext context, KeyEvent event) {
    if (event is KeyUpEvent) return KeyEventResult.ignored;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.enter ||
        key == LogicalKeyboardKey.numpadEnter) {
      Navigator.of(context).pop(true);
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.escape) {
      Navigator.of(context).pop(false);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  @override
  Widget build(BuildContext context) => Focus(
    autofocus: true,
    onKeyEvent: (_, event) => _key(context, event),
    child: AlertDialog(
      title: const Text('Imprimir a NFC-e?'),
      content: Text(summary),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancelar (Esc)'),
        ),
        FilledButton.icon(
          onPressed: () => Navigator.of(context).pop(true),
          icon: const Icon(Icons.print_outlined),
          label: const Text('Imprimir (Enter)'),
        ),
      ],
    ),
  );
}
