import 'package:flutter/material.dart';

import '../../../core/formatters/value_formatters.dart';

/// `‹ 3 › un` embaixo do nome do produto.
///
/// Fica fora do card porque é o único pedaço dele com COMPORTAMENTO: os dois
/// botões mudam a quantidade, e o resto só desenha. Quem for mexer no passo do
/// contador abre este arquivo e não precisa ler o cartão inteiro.
class CartQuantityStepper extends StatelessWidget {
  const CartQuantityStepper({
    super.key,
    required this.quantity,
    required this.onDelta,
  });

  final dynamic quantity;
  final ValueChanged<int> onDelta;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final atual = ValueFormatters.number(quantity);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _botao(
          context,
          icon: Icons.remove_rounded,
          // Um a menos que 1 é zero, e zero é cancelar — o mesmo caminho do
          // "×", com motivo e registro. O botão não some nessa hora: sumir
          // faria o operador procurar outro jeito de tirar o item.
          tooltip: atual <= 1 ? 'Cancelar item' : 'Uma unidade a menos',
          onPressed: () => onDelta(-1),
        ),
        SizedBox(
          width: 34,
          child: Text(
            atual.toStringAsFixed(0),
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w900),
          ),
        ),
        _botao(
          context,
          icon: Icons.add_rounded,
          tooltip: 'Uma unidade a mais',
          onPressed: () => onDelta(1),
        ),
        const SizedBox(width: 4),
        Text(
          'un',
          style: TextStyle(
            color: scheme.onSurfaceVariant,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }

  Widget _botao(
    BuildContext context, {
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: InkResponse(
        onTap: onPressed,
        radius: 17,
        child: Container(
          width: 26,
          height: 26,
          decoration: BoxDecoration(
            border: Border.all(color: scheme.outlineVariant),
            borderRadius: BorderRadius.circular(7),
          ),
          child: Icon(icon, size: 15, color: scheme.onSurface),
        ),
      ),
    );
  }
}
