import 'package:flutter/material.dart';

import '../../../core/formatters/value_formatters.dart';
import '../data/order_merge_repository.dart';

/// As peças da tela de conta agrupada, separadas do diálogo que as arranja.
///
/// Elas existem porque a conferência com o cliente acontece **item a item, em
/// voz alta** — e é ela que pega o engano antes de virar discussão. Mostrar só
/// o total deixaria essa conferência sem onde acontecer.

/// O campo do leitor de código de barras.
///
/// O leitor é um teclado: ele digita o código e manda um Enter. Por isso o
/// campo é alto e com fonte grande (o cartão é passado sem olhar, e a
/// conferência visual acontece de longe, com o cliente do outro lado do balcão)
/// e o Enter vira "incluir esta comanda".
class MergeScannerField extends StatelessWidget {
  const MergeScannerField({
    super.key,
    required this.controller,
    required this.focusNode,
    required this.onSubmit,
    this.enabled = true,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final VoidCallback onSubmit;
  final bool enabled;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Expanded(
        child: TextField(
          controller: controller,
          focusNode: focusNode,
          enabled: enabled,
          autofocus: true,
          style: const TextStyle(fontSize: 18),
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.qr_code_scanner_rounded),
            labelText: 'Passe o cartão ou digite o número da comanda',
            helperText: 'Bipar a mesma comanda de novo não duplica nada.',
          ),
          onSubmitted: (_) => onSubmit(),
        ),
      ),
      const SizedBox(width: 12),
      FilledButton(
        onPressed: enabled ? onSubmit : null,
        child: const Text('Incluir'),
      ),
    ],
  );
}

/// O motivo da recusa — e se vale tentar de novo.
class MergeErrorBanner extends StatelessWidget {
  const MergeErrorBanner({
    super.key,
    required this.message,
    this.conflict = false,
  });

  final String message;

  /// 409: outro caixa chegou antes, ou o estado mudou embaixo da tela. Tem
  /// cor própria porque tentar de novo com o mesmo cartão nunca resolve.
  final bool conflict;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fundo = conflict ? scheme.errorContainer : scheme.secondaryContainer;
    final texto = conflict ? scheme.onErrorContainer : scheme.onSecondaryContainer;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: fundo,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Icon(
            conflict ? Icons.lock_clock_rounded : Icons.info_outline_rounded,
            size: 18,
            color: texto,
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(message, style: TextStyle(color: texto))),
        ],
      ),
    );
  }
}

/// Os itens da conta, agrupados por comanda.
class MergeGroupList extends StatelessWidget {
  const MergeGroupList({
    super.key,
    required this.groups,
    required this.onRemove,
    required this.onReceipt,
    this.removable = false,
    this.enabled = true,
  });

  final List<MergeCommandGroup> groups;
  final ValueChanged<String> onRemove;

  /// Imprimir a conferência DESTA comanda. É o papel que o cliente pede — "e a
  /// comanda 13, quanto deu?" — dentro de uma conta de quatro pessoas.
  final ValueChanged<String> onReceipt;

  final bool removable;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    if (groups.isEmpty) {
      return const Center(child: Text('Nenhum item nesta conta ainda.'));
    }
    return ListView.separated(
      itemCount: groups.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, index) => _Group(
        group: groups[index],
        removable: removable,
        enabled: enabled,
        onRemove: onRemove,
        onReceipt: onReceipt,
      ),
    );
  }
}

class _Group extends StatelessWidget {
  const _Group({
    required this.group,
    required this.removable,
    required this.enabled,
    required this.onRemove,
    required this.onReceipt,
  });

  final MergeCommandGroup group;
  final bool removable;
  final bool enabled;
  final ValueChanged<String> onRemove;
  final ValueChanged<String> onReceipt;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            color: scheme.surfaceContainerHighest,
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    'Comanda ${group.number ?? ''}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                Text(ValueFormatters.money(group.total)),
                const SizedBox(width: 8),
                TextButton(
                  onPressed: enabled ? () => onReceipt(group.commandId) : null,
                  child: const Text('Conferência'),
                ),
                if (removable) ...[
                  const SizedBox(width: 8),
                  TextButton(
                    onPressed: enabled ? () => onRemove(group.commandId) : null,
                    child: const Text('Retirar'),
                  ),
                ],
              ],
            ),
          ),
          for (final item in group.items)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: Row(
                children: [
                  SizedBox(
                    width: 64,
                    child: Text('${item['quantity'] ?? ''}'),
                  ),
                  Expanded(child: Text('${item['product_name'] ?? ''}')),
                  Text(ValueFormatters.money(item['total_price'])),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// O resumo da conta: quantas comandas, quanto deu e por quê.
class MergeSummaryPanel extends StatelessWidget {
  const MergeSummaryPanel({super.key, required this.merge});

  final Map<String, dynamic>? merge;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final sources = (merge?['sources'] as List? ?? const []).length;
    final items = (merge?['items'] as List? ?? const []).length;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('Resumo', style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 10),
          _Line(label: 'Comandas', value: '$sources'),
          _Line(label: 'Itens', value: '$items'),
          _Line(label: 'Subtotal', value: ValueFormatters.money(merge?['subtotal'])),
          _Line(label: 'Serviço', value: ValueFormatters.money(merge?['service_fee'])),
          _Line(label: 'Desconto', value: ValueFormatters.money(merge?['discount'])),
          const Divider(height: 20),
          Row(
            children: [
              const Expanded(child: Text('Total')),
              Text(
                ValueFormatters.money(merge?['total']),
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            'A taxa é a soma das taxas de cada comanda, já arredondadas — '
            'não um percentual novo sobre o total.',
            style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 3),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(value),
      ],
    ),
  );
}
