import 'package:flutter/material.dart';

/// "O peso na balança é o do prato já lançado" — e a saída, se não for.
///
/// Depois de lançar, o mesmo peso é ignorado para o prato que ficou na
/// balança não ser cobrado de novo. Sem dizer isso, a tela mostrava 0 com
/// "Peso estável" no rodapé, e o operador achava que a balança tinha travado.
class RetainedWeightNotice extends StatelessWidget {
  const RetainedWeightNotice({
    super.key,
    required this.pesoKg,
    required this.onPesarDeNovo,
  });

  /// O peso que está sendo ignorado; nulo enquanto nenhuma leitura chegou.
  final double? pesoKg;
  final VoidCallback onPesarDeNovo;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final peso = pesoKg;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        children: [
          Text(
            peso == null
                ? 'Retire o prato lançado para a próxima pesagem.'
                : 'Na balança: ${peso.toStringAsFixed(3)} kg, o mesmo peso do '
                      'prato já lançado. Retire o prato — ou, se é outro '
                      'prato, toque em "Pesar de novo".',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: onPesarDeNovo,
            icon: const Icon(Icons.scale_rounded),
            label: const Text('Pesar de novo'),
          ),
        ],
      ),
    );
  }
}
