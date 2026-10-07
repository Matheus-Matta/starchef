import 'package:flutter/material.dart';

import '../../../core/input/command_code_match.dart';

/// A comanda lida e o total, em letras GRANDES, na coluna da direita.
///
/// O cliente confere de longe, antes de tirar o prato, se o número é o do
/// cartão dele e quanto deu. Em letra de 12 pontos ninguém conferia — e a
/// leitura errada (o 17 virando 107) só aparecia depois de lançada.
///
/// Sem [commandCode] (ainda não leu), mostra só o total a lançar.
class ScaleCommandHighlight extends StatelessWidget {
  const ScaleCommandHighlight({
    super.key,
    required this.totalLabel,
    this.commandCode,
    this.status,
    this.statusIcon,
  });

  final String totalLabel;
  final String? commandCode;
  final String? status;
  final Widget? statusIcon;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final codigo = commandCode?.trim() ?? '';
    final rotulo = TextStyle(
      fontSize: 15,
      fontWeight: FontWeight.w800,
      letterSpacing: 4,
      color: scheme.onSurfaceVariant,
    );
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (codigo.isNotEmpty) ...[
          Text('COMANDA', textAlign: TextAlign.center, style: rotulo),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              numeroLidoParaExibir(codigo),
              key: const ValueKey('balanca-comanda-numero'),
              style: TextStyle(
                fontSize: 96,
                height: 1.05,
                fontWeight: FontWeight.w900,
                color: scheme.primary,
              ),
            ),
          ),
          const SizedBox(height: 12),
        ],
        Text(
          codigo.isEmpty ? 'TOTAL A LANÇAR' : 'TOTAL',
          textAlign: TextAlign.center,
          style: rotulo,
        ),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(
            totalLabel,
            key: const ValueKey('balanca-comanda-total'),
            style: TextStyle(
              fontSize: 48,
              fontWeight: FontWeight.w900,
              color: scheme.onSurface,
            ),
          ),
        ),
        if (status != null) ...[
          const SizedBox(height: 16),
          ?statusIcon,
          if (statusIcon != null) const SizedBox(height: 8),
          Text(
            status!,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
          ),
        ],
      ],
    );
  }
}
