import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'command_labels.dart';

/// Escolhe a faixa de números: "da comanda 10 até a 100".
class FaixaDeEtiquetasDialog extends StatefulWidget {
  const FaixaDeEtiquetasDialog({super.key, this.de, this.ate});

  /// Sugestões (a menor e a maior comanda carregadas na tela).
  final int? de;
  final int? ate;

  @override
  State<FaixaDeEtiquetasDialog> createState() => _FaixaDeEtiquetasDialogState();
}

class _FaixaDeEtiquetasDialogState extends State<FaixaDeEtiquetasDialog> {
  late final _de = TextEditingController(text: widget.de?.toString() ?? '1');
  late final _ate = TextEditingController(text: widget.ate?.toString() ?? '');
  String _erro = '';

  @override
  void dispose() {
    _de.dispose();
    _ate.dispose();
    super.dispose();
  }

  void _continuar() {
    final faixa = faixaValida(
      _de.text,
      _ate.text,
      (mensagem) => setState(() => _erro = mensagem),
    );
    if (faixa != null) Navigator.of(context).pop(faixa);
  }

  Widget _campo(TextEditingController controle, String rotulo) => Expanded(
    child: TextField(
      controller: controle,
      keyboardType: TextInputType.number,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
      decoration: InputDecoration(labelText: rotulo, isDense: true),
      onSubmitted: (_) => _continuar(),
    ),
  );

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Imprimir etiquetas de comanda'),
    content: SizedBox(
      width: 420,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Uma etiqueta por comanda: o número grande no topo, o QR Code e o '
            'código de barras. Saem uma a uma, na impressora que você escolher.',
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _campo(_de, 'Da comanda'),
              const SizedBox(width: 12),
              _campo(_ate, 'Até a comanda'),
            ],
          ),
          if (_erro.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              _erro,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Cancelar'),
      ),
      FilledButton.icon(
        onPressed: _continuar,
        icon: const Icon(Icons.print_rounded),
        label: const Text('Continuar'),
      ),
    ],
  );
}

/// "Etiqueta 12 de 91 — comanda 21", com o botão de parar.
class ProgressoDasEtiquetas extends StatelessWidget {
  const ProgressoDasEtiquetas({
    super.key,
    required this.total,
    required this.feitas,
    required this.atual,
    required this.onParar,
  });

  final int total;
  final ValueListenable<int> feitas;
  final ValueListenable<String> atual;
  final VoidCallback onParar;

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Imprimindo etiquetas'),
    content: SizedBox(
      width: 380,
      child: ValueListenableBuilder<int>(
        valueListenable: feitas,
        builder: (context, n, _) => Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ValueListenableBuilder<String>(
              valueListenable: atual,
              builder: (context, numero, _) => Text(
                'Etiqueta ${n < total ? n + 1 : total} de $total — comanda $numero',
              ),
            ),
            const SizedBox(height: 12),
            LinearProgressIndicator(value: total == 0 ? null : n / total),
          ],
        ),
      ),
    ),
    actions: [
      OutlinedButton.icon(
        onPressed: onParar,
        icon: const Icon(Icons.stop_rounded),
        label: const Text('Parar'),
      ),
    ],
  );
}
