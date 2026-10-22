import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import 'atalhos_das_paginas.dart';
import 'pdv_navigation_shell.dart';

/// Um botão do trilho de navegação (`pdv_navigation_rail.dart`): ícone,
/// nome e, no canto, a tecla de função da página.
class RailButton extends StatelessWidget {
  const RailButton({
    super.key,
    required this.entry,
    required this.selected,
    required this.onTap,
  });

  final RailEntry entry;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final foreground = selected ? scheme.primary : scheme.onSurfaceVariant;
    final tecla = teclaDaPagina(entry.destination);
    return Tooltip(
      message: tecla.isEmpty ? entry.label : '${entry.label} ($tecla)',
      waitDuration: const Duration(milliseconds: 350),
      child: Material(
        color: selected ? scheme.primaryContainer : Colors.transparent,
        borderRadius: AppTheme.radius,
        child: InkWell(
          onTap: onTap,
          borderRadius: AppTheme.radius,
          focusColor: scheme.primaryContainer,
          child: Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              border: selected
                  ? Border(left: BorderSide(color: scheme.primary, width: 3))
                  : null,
            ),
            child: Stack(
              children: [
                // A tecla da página no canto: quem olha o menu aprende o atalho.
                if (tecla.isNotEmpty)
                  Positioned(
                    top: 3,
                    right: 5,
                    child: Text(
                      tecla,
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 8.5,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                Center(child: _conteudo(foreground)),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _conteudo(Color foreground) => Column(
    mainAxisAlignment: MainAxisAlignment.center,
    children: [
      Icon(entry.icon, size: 21, color: foreground),
      const SizedBox(height: 3),
      Text(
        entry.label,
        maxLines: 1,
        style: TextStyle(
          color: foreground,
          fontSize: 10,
          fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
        ),
      ),
    ],
  );
}

class RailEntry {
  const RailEntry(this.destination, this.label, this.icon);

  final PdvDestination destination;
  final String label;
  final IconData icon;
}
