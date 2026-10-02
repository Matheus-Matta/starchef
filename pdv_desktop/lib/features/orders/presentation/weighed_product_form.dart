import 'package:flutter/material.dart';

import '../../../core/formatters/decimal_money.dart';
import '../../../core/formatters/value_formatters.dart';
import 'weighed_product_math.dart';

class WeighedProductForm extends StatelessWidget {
  const WeighedProductForm({
    required this.mode,
    required this.entryController,
    required this.noteController,
    required this.scales,
    required this.scaleId,
    required this.onModeChanged,
    required this.onScaleChanged,
    required this.onReadScale,
    required this.readingScale,
    required this.weightGrams,
    required this.totalCents,
    required this.message,
    super.key,
  });

  final WeighedProductEntryMode mode;
  final TextEditingController entryController;
  final TextEditingController noteController;
  final List<Map<String, dynamic>> scales;
  final String? scaleId;
  final ValueChanged<WeighedProductEntryMode> onModeChanged;
  final ValueChanged<String?> onScaleChanged;
  final VoidCallback onReadScale;
  final bool readingScale;
  final int weightGrams;
  final int totalCents;
  final String? message;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      SegmentedButton<WeighedProductEntryMode>(
        segments: const [
          ButtonSegment(
            value: WeighedProductEntryMode.weight,
            label: Text('Peso'),
            icon: Icon(Icons.scale_outlined),
          ),
          ButtonSegment(
            value: WeighedProductEntryMode.amount,
            label: Text('Valor'),
            icon: Icon(Icons.payments_outlined),
          ),
        ],
        selected: {mode},
        onSelectionChanged: (value) => onModeChanged(value.single),
      ),
      const SizedBox(height: 12),
      TextField(
        key: const Key('weighed-product-entry'),
        controller: entryController,
        autofocus: true,
        textAlign: TextAlign.center,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        style: const TextStyle(fontSize: 38, fontWeight: FontWeight.w800),
        decoration: InputDecoration(
          labelText: mode == WeighedProductEntryMode.weight
              ? 'Peso do produto'
              : 'Valor desejado',
          hintText: mode == WeighedProductEntryMode.weight ? '0,000' : '0,00',
          suffixText: mode == WeighedProductEntryMode.weight ? 'kg' : r'R$',
        ),
      ),
      if (scales.length > 1) ...[
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          initialValue: scaleId,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Balança'),
          items: scales
              .map(
                (scale) => DropdownMenuItem(
                  value: '${scale['id']}',
                  child: Text('${scale['name']}'),
                ),
              )
              .toList(),
          onChanged: onScaleChanged,
        ),
      ],
      if (scales.isNotEmpty) ...[
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: scaleId == null || readingScale ? null : onReadScale,
          icon: readingScale
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.scale_outlined),
          label: Text(readingScale ? 'Lendo...' : 'Ler da balança'),
        ),
      ],
      if (weightGrams > 0) ...[
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '${(weightGrams / 1000).toStringAsFixed(3).replaceAll('.', ',')} kg',
            ),
            Text(
              ValueFormatters.money(DecimalMoney.asNumber(totalCents)),
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
          ],
        ),
        if (mode == WeighedProductEntryMode.amount)
          const Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Peso aproximado; o valor final considera o peso ao grama.',
              style: TextStyle(fontSize: 11),
            ),
          ),
      ],
      if (message != null) ...[
        const SizedBox(height: 8),
        Text(
          message!,
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
      ],
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('Observação (opcional)'),
        children: [
          TextField(
            controller: noteController,
            maxLines: 2,
            decoration: const InputDecoration(
              hintText: 'Ex.: retirar excesso de gordura',
            ),
          ),
        ],
      ),
    ],
  );
}

class WeighedProductTitle extends StatelessWidget {
  const WeighedProductTitle({required this.product, super.key});

  final Map<String, dynamic> product;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('${product['name']}'),
      Text(
        '${ValueFormatters.money(product['current_price'])} / kg',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ],
  );
}
