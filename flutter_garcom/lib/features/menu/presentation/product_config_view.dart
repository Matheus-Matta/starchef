import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../orders/presentation/order_formatters.dart';
import '../domain/product_options.dart';

/// Segunda etapa do lançamento: variação, adicionais, quantidade e observação.
///
/// Mesma pergunta que o PDV desktop faz (`product_config_dialog.dart`), só que
/// numa folha em vez de um diálogo.
class ProductConfigView extends StatefulWidget {
  const ProductConfigView({
    super.key,
    required this.product,
    required this.onBack,
    required this.onConfirm,
  });

  final Map<String, dynamic> product;
  final VoidCallback onBack;
  final ValueChanged<ProductChoice> onConfirm;

  @override
  State<ProductConfigView> createState() => _ProductConfigViewState();
}

class _ProductConfigViewState extends State<ProductConfigView> {
  final _note = TextEditingController();
  final _selectedAddons = <String>{};
  int _quantity = 1;
  String? _variationId;

  late final List<Map<String, dynamic>> _variations = activeVariations(
    widget.product,
  );
  late final List<Map<String, dynamic>> _addons = activeAddons(widget.product);
  late final bool _variationRequired = requiresVariation(widget.product);

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  String? get _variationName {
    for (final variation in _variations) {
      if ('${variation['id']}' == _variationId) {
        return '${variation['name'] ?? ''}';
      }
    }
    return null;
  }

  bool get _missingVariation =>
      _variationRequired && (_variationId ?? '').isEmpty;

  double get _unitPrice => expectedUnitPrice(
    widget.product,
    variationId: _variationId,
    addonIds: _selectedAddons,
  );

  void _confirm() => widget.onConfirm(
    ProductChoice(
      productId: '${widget.product['id']}',
      productName: '${widget.product['name'] ?? ''}',
      quantity: _quantity,
      variationId: _variationId,
      variationName: _variationName,
      addonIds: _selectedAddons.toList(),
      note: _note.text.trim(),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(),
          if (_variations.isNotEmpty) ...[
            const SizedBox(height: 18),
            _Label(_variationRequired ? 'Variação (obrigatória)' : 'Variação'),
            _variationList(scheme),
          ],
          if (_addons.isNotEmpty) ...[
            const SizedBox(height: 8),
            const _Label('Adicionais'),
            ..._addons.map((item) => _addonTile(item, scheme)),
          ],
          const SizedBox(height: 20),
          _QuantityStepper(
            quantity: _quantity,
            onChanged: (value) => setState(() => _quantity = value),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _note,
            maxLines: 3,
            decoration: const InputDecoration(
              labelText: 'Observação para a cozinha',
              hintText: 'Ex.: sem cebola, ponto da carne...',
              alignLabelWithHint: true,
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'Total do item: ${money(_unitPrice * _quantity)}',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          // Sem esta trava o item era lançado sem variação, entrava na fila e
          // só falhava lá na frente, ao chegar no servidor: o garçom via
          // "Selecione uma variação obrigatória" numa pendência de meia hora
          // atrás, sem saber mais de que item se tratava.
          if (_missingVariation)
            Padding(
              padding: const EdgeInsets.only(bottom: AppTheme.gap),
              child: Text(
                'Escolha uma variação para lançar este produto.',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.error, fontSize: 13),
              ),
            ),
          ShadButton(
            height: AppTheme.controlHeight,
            leading: const Icon(Icons.check, size: 18),
            enabled: !_missingVariation,
            onPressed: _confirm,
            child: const Text('Lançar no pedido'),
          ),
        ],
      ),
    );
  }

  Widget _header() => Row(
    children: [
      IconButton(onPressed: widget.onBack, icon: const Icon(Icons.arrow_back)),
      Expanded(
        child: Text(
          '${widget.product['name'] ?? ''}',
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
        ),
      ),
      Text(money(widget.product['sale_price'])),
    ],
  );

  Widget _variationList(ColorScheme scheme) => RadioGroup<String>(
    groupValue: _variationId,
    onChanged: (value) => setState(() => _variationId = value),
    child: Column(
      children: [
        for (final item in _variations)
          RadioListTile<String>(
            contentPadding: EdgeInsets.zero,
            dense: true,
            value: '${item['id']}',
            title: Text('${item['name']}'),
            secondary: Text(
              '+ ${money(item['price_delta'])}',
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
          ),
      ],
    ),
  );

  Widget _addonTile(Map<String, dynamic> item, ColorScheme scheme) {
    final id = '${item['id']}';
    return CheckboxListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      controlAffinity: ListTileControlAffinity.leading,
      value: _selectedAddons.contains(id),
      onChanged: (checked) => setState(() {
        if (checked == true) {
          _selectedAddons.add(id);
        } else {
          _selectedAddons.remove(id);
        }
      }),
      title: Text('${item['name']}'),
      secondary: Text(
        '+ ${money(item['price'])}',
        style: TextStyle(color: scheme.onSurfaceVariant),
      ),
    );
  }
}

class _QuantityStepper extends StatelessWidget {
  const _QuantityStepper({required this.quantity, required this.onChanged});

  final int quantity;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) => Row(
    mainAxisAlignment: MainAxisAlignment.center,
    children: [
      IconButton.outlined(
        iconSize: 28,
        onPressed: quantity > 1 ? () => onChanged(quantity - 1) : null,
        icon: const Icon(Icons.remove),
      ),
      SizedBox(
        width: 90,
        child: Text(
          '$quantity',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w800),
        ),
      ),
      IconButton.outlined(
        iconSize: 28,
        onPressed: () => onChanged(quantity + 1),
        icon: const Icon(Icons.add),
      ),
    ],
  );
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 2),
    child: Text(
      text,
      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
    ),
  );
}
