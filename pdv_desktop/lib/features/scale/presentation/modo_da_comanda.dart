import 'package:flutter/material.dart';

/// Escolha, ao iniciar a estação, de COMO a pesagem acha a comanda.
///
/// - **Ler comanda**: o cliente passa o cartão depois de pesar (o de sempre).
/// - **Comanda automática**: a balança lança sozinha na próxima comanda livre,
///   em ordem crescente (1, 2, 3 ... e volta ao início). Quem escolhe o
///   número é o servidor, numa fila única para todas as balanças — duas
///   balanças nunca usam o mesmo número (`fila_da_comanda.py`).
class ModoDaComandaSelector extends StatelessWidget {
  const ModoDaComandaSelector({
    super.key,
    required this.automatica,
    required this.onMudou,
  });

  final bool automatica;
  final ValueChanged<bool> onMudou;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      SegmentedButton<bool>(
        segments: const [
          ButtonSegment(
            value: false,
            icon: Icon(Icons.qr_code_scanner),
            label: Text('Ler comanda'),
          ),
          ButtonSegment(
            value: true,
            icon: Icon(Icons.format_list_numbered),
            label: Text('Comanda automática'),
          ),
        ],
        selected: {automatica},
        onSelectionChanged: (escolha) => onMudou(escolha.first),
      ),
      const SizedBox(height: 6),
      Text(
        automatica
            ? 'Pesou, lançou: o prato vai para a próxima comanda livre, em '
                  'ordem crescente. Comanda ocupada é pulada; depois da última, '
                  'volta para a primeira.'
            : 'O cliente passa o cartão da comanda depois de pesar.',
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: 12,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
    ],
  );
}

/// Liga a pergunta "qual produto?" depois de cada pesagem.
class EscolherProdutoSwitch extends StatelessWidget {
  const EscolherProdutoSwitch({
    super.key,
    required this.ligado,
    required this.onMudou,
  });

  final bool ligado;
  final ValueChanged<bool> onMudou;

  @override
  Widget build(BuildContext context) => SwitchListTile(
    value: ligado,
    onChanged: onMudou,
    title: const Text('Escolher o produto a cada pesagem'),
    subtitle: const Text(
      'Ignora o produto da balança: depois do peso, escolha entre os '
      'produtos por quilo com ↑ ↓ e Enter.',
    ),
  );
}

/// O painel da comanda no modo automático, enquanto espera o prato.
class ComandaAutomaticaAguardando extends StatelessWidget {
  const ComandaAutomaticaAguardando({super.key, this.ultima});

  /// Última comanda lançada por esta estação (só informativo).
  final String? ultima;

  @override
  Widget build(BuildContext context) {
    final cor = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Column(
        children: [
          Icon(Icons.format_list_numbered, size: 30, color: cor),
          const SizedBox(height: 8),
          Text(
            'Comanda automática: pese o prato e ele entra na próxima '
            'comanda livre.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: cor),
          ),
          if (ultima != null) ...[
            const SizedBox(height: 8),
            Text(
              'Última lançada: comanda $ultima',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ],
      ),
    );
  }
}
