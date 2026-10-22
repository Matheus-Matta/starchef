import 'package:flutter/material.dart';

import '../../../core/input/pdv_screen.dart';
import '../../../core/input/pdv_shortcuts.dart';

class PdvShortcutBar extends StatelessWidget {
  const PdvShortcutBar({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 30,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: [
          // Do catálogo, e não texto solto: "F4  Pagamento" ficou escrito
          // aqui depois de a tecla mudar.
          _keys(PdvShortcuts.teclaDe(PdvAction.focusSearch), 'Buscar'),
          _keys('+ / −', 'Quantidade'),
          _keys(
            PdvShortcuts.teclaDe(PdvAction.payment, screen: PdvScreen.order),
            'Pagamento',
          ),
          _keys(PdvShortcuts.teclaDe(PdvAction.sendToKitchen), 'Cozinha'),
          _keys(PdvShortcuts.teclaDe(PdvAction.back), 'Voltar'),
          const Spacer(),
          if (message != null)
            Flexible(
              child: Text(
                message!,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.right,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _keys(String key, String action) => Padding(
    padding: const EdgeInsets.only(right: 18),
    child: Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: key,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          TextSpan(text: '  $action'),
        ],
      ),
      style: const TextStyle(fontSize: 12),
    ),
  );
}
