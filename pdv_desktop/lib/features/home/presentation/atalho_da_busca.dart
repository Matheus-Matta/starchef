import 'package:flutter/material.dart';

import '../../../core/input/pdv_shortcuts.dart';

/// A tecla que leva à busca, escrita dentro do campo de busca da venda.
/// Lida do catálogo (`PdvShortcuts.teclaDe`): muda junto com a tecla.
class AtalhoDaBusca extends StatelessWidget {
  const AtalhoDaBusca({super.key});

  @override
  Widget build(BuildContext context) => Center(
    widthFactor: 1,
    child: Text(
      PdvShortcuts.teclaDe(PdvAction.focusSearch),
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: 11,
        fontWeight: FontWeight.w800,
      ),
    ),
  );
}
