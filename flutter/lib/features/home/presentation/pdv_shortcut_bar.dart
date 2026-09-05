import 'package:flutter/material.dart';

import '../../../core/input/pdv_screen.dart';
import '../../../core/input/pdv_shortcuts.dart';

/// A faixa de atalhos do rodapé, contextual à tela.
///
/// Nasce do MESMO catálogo que o roteador usa (`PdvShortcuts.all`), filtrado
/// pela tela atual. Não há segunda lista para desencontrar: um atalho novo
/// aparece aqui no mesmo commit em que passa a funcionar, e um que só vale no
/// pagamento não polui a tela de vendas.
///
/// É deliberadamente rasa — o operador olha para o pedido, não para cá. Ela
/// serve para a tecla ser DESCOBERTA sem abrir a ajuda, e para isso basta
/// estar no canto do olho.
class PdvShortcutBar extends StatelessWidget {
  const PdvShortcutBar({
    super.key,
    required this.screen,
    this.hasOrder = false,
  });

  final PdvScreen screen;

  /// Sem pedido aberto, os atalhos que dependem dele aparecem apagados em vez
  /// de sumir: a tecla continua existindo, e o operador aprende quando ela
  /// vale em vez de achar que ela some sozinha.
  final bool hasOrder;

  /// Altura total da faixa. Rasa de propósito.
  static const height = 20.0;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final atalhos = [
      for (final atalho in PdvShortcuts.all)
        if (atalho.appliesTo(screen)) atalho,
    ];
    if (atalhos.isEmpty) return const SizedBox.shrink();

    return Container(
      height: height,
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 10),
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: atalhos.length,
        separatorBuilder: (_, _) => _separador(scheme),
        itemBuilder: (_, index) => _item(scheme, atalhos[index]),
      ),
    );
  }

  Widget _separador(ColorScheme scheme) => Padding(
    padding: const EdgeInsets.symmetric(horizontal: 7),
    child: Center(
      child: Text(
        '·',
        style: TextStyle(fontSize: 10, color: scheme.onSurfaceVariant),
      ),
    ),
  );

  Widget _item(ColorScheme scheme, PdvShortcut atalho) {
    final disponivel = hasOrder || !atalho.requiresOrder;
    final cor = disponivel
        ? scheme.onSurfaceVariant
        : scheme.onSurfaceVariant.withValues(alpha: .38);
    return Center(
      child: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: atalho.keysLabel,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w900,
                color: disponivel ? scheme.primary : cor,
              ),
            ),
            const TextSpan(text: '  '),
            TextSpan(
              text: atalho.label,
              style: TextStyle(fontSize: 10, color: cor),
            ),
          ],
        ),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}
