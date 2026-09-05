import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../theme/app_theme.dart';

/// Os dois blocos que todo formulário do app repete: campos que se acomodam
/// à largura, e o botão de confirmar com o estado de "trabalhando" embutido.

/// Mantém campos relacionados lado a lado em telas largas e os empilha quando
/// cada controle ficaria estreito demais para rótulo, sufixo e validação.
///
/// O mesmo widget do desktop — no celular ele quase sempre empilha, e é
/// exatamente esse "quase" que importa: o aparelho deitado, ou um tablet no
/// balcão, ganha a linha única sem a tela precisar saber disso.
class AppResponsiveFields extends StatelessWidget {
  const AppResponsiveFields({
    super.key,
    required this.children,
    this.breakpoint = 360,
    this.spacing = AppTheme.gap,
    this.flex = const [],
  });

  final List<Widget> children;
  final double breakpoint;
  final double spacing;
  final List<int> flex;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      if (constraints.maxWidth < breakpoint) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var index = 0; index < children.length; index++) ...[
              if (index > 0) SizedBox(height: spacing),
              children[index],
            ],
          ],
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var index = 0; index < children.length; index++) ...[
            if (index > 0) SizedBox(width: spacing),
            Expanded(
              flex: index < flex.length ? flex[index] : 1,
              child: children[index],
            ),
          ],
        ],
      );
    },
  );
}

/// Botão principal de um formulário, com o estado de "trabalhando" embutido.
///
/// Trocar o ícone por um progresso circular e o rótulo por outro texto era o
/// mesmo bloco de catorze linhas nas duas telas de entrada, cada uma com um
/// tamanho de indicador.
class AppSubmitButton extends StatelessWidget {
  const AppSubmitButton({
    super.key,
    required this.label,
    required this.icon,
    required this.onPressed,
    this.busyLabel,
    this.busy = false,
  });

  final String label;

  /// Rótulo enquanto a ação acontece. Sem ele, o rótulo não muda.
  final String? busyLabel;

  final IconData icon;
  final VoidCallback onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) => ShadButton(
    onPressed: onPressed,
    enabled: !busy,
    height: AppTheme.controlHeight,
    leading: busy
        ? const SizedBox.square(
            dimension: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: Colors.white,
            ),
          )
        : Icon(icon, size: 18),
    child: Text(busy ? (busyLabel ?? label) : label),
  );
}
