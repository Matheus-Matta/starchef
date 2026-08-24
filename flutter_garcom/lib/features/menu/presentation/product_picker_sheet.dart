import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../orders/presentation/order_formatters.dart';

/// O que o garçom escolheu lançar na mesa.
class ProductChoice {
  const ProductChoice({
    required this.productId,
    required this.quantity,
    this.note = '',
  });

  final String productId;
  final int quantity;
  final String note;
}

/// Busca do catálogo + quantidade + observação, em uma folha só.
///
/// Uma tela por escolha atrasaria o atendimento: o garçom está em pé na mesa,
/// com o cliente esperando. Busca por nome porque decorar código de produto é
/// coisa de operador de caixa, não de salão.
Future<ProductChoice?> showProductPicker(
  BuildContext context,
  List<Map<String, dynamic>> products,
) => showModalBottomSheet<ProductChoice>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(
      bottom: MediaQuery.of(context).viewInsets.bottom,
    ),
    child: _ProductPicker(products: products),
  ),
);

class _ProductPicker extends StatefulWidget {
  const _ProductPicker({required this.products});

  final List<Map<String, dynamic>> products;

  @override
  State<_ProductPicker> createState() => _ProductPickerState();
}

class _ProductPickerState extends State<_ProductPicker> {
  final _search = TextEditingController();
  final _note = TextEditingController();
  Map<String, dynamic>? _selected;
  int _quantity = 1;

  @override
  void dispose() {
    _search.dispose();
    _note.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> get _matches {
    final term = _search.text.trim().toLowerCase();
    final available = widget.products.where(_sellable);
    if (term.isEmpty) return available.toList(growable: false);
    return available
        .where(
          (product) =>
              '${product['name'] ?? ''}'.toLowerCase().contains(term) ||
              '${product['internal_code'] ?? ''}'.toLowerCase().contains(term),
        )
        .toList(growable: false);
  }

  /// Adicional e insumo não são vendidos sozinhos, e produto por kilo depende
  /// da balança do balcão — nenhum dos três cabe no lançamento pelo celular.
  static bool _sellable(Map<String, dynamic> product) =>
      product['product_type'] != 'addon' &&
      product['product_type'] != 'input' &&
      product['pricing_unit'] != 'kg';

  @override
  Widget build(BuildContext context) {
    final height = MediaQuery.of(context).size.height * .82;
    return SizedBox(
      height: height,
      child: _selected == null ? _buildList() : _buildConfig(),
    );
  }

  Widget _buildList() {
    final matches = _matches;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
          child: TextField(
            controller: _search,
            autofocus: true,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              hintText: 'Buscar produto',
              prefixIcon: const Icon(Icons.search),
              border: OutlineInputBorder(borderRadius: AppTheme.radius),
            ),
          ),
        ),
        if (matches.isEmpty)
          const Expanded(
            child: Center(child: Text('Nenhum produto encontrado.')),
          )
        else
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
              itemCount: matches.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final product = matches[index];
                return InkWell(
                  borderRadius: AppTheme.radius,
                  onTap: () => setState(() {
                    _selected = product;
                    _quantity = 1;
                    _note.clear();
                  }),
                  child: ShadCard(
                    radius: AppTheme.radius,
                    columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${product['name'] ?? ''}',
                            style: const TextStyle(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Text(money(product['sale_price'])),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
      ],
    );
  }

  Widget _buildConfig() {
    final product = _selected!;
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconButton(
                onPressed: () => setState(() => _selected = null),
                icon: const Icon(Icons.arrow_back),
              ),
              Expanded(
                child: Text(
                  '${product['name'] ?? ''}',
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(money(product['sale_price'])),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              IconButton.outlined(
                iconSize: 28,
                onPressed: _quantity > 1
                    ? () => setState(() => _quantity -= 1)
                    : null,
                icon: const Icon(Icons.remove),
              ),
              SizedBox(
                width: 90,
                child: Text(
                  '$_quantity',
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              IconButton.outlined(
                iconSize: 28,
                onPressed: () => setState(() => _quantity += 1),
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _note,
            maxLines: 3,
            decoration: InputDecoration(
              labelText: 'Observação para a cozinha',
              hintText: 'Ex.: sem cebola, ponto da carne...',
              alignLabelWithHint: true,
              border: OutlineInputBorder(borderRadius: AppTheme.radius),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'Total do item: '
            '${money(amount(product['sale_price']) * _quantity)}',
            textAlign: TextAlign.center,
            style: TextStyle(color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 12),
          ShadButton(
            height: AppTheme.controlHeight,
            leading: const Icon(Icons.check, size: 18),
            onPressed: () => Navigator.of(context).pop(
              ProductChoice(
                productId: '${product['id']}',
                quantity: _quantity,
                note: _note.text.trim(),
              ),
            ),
            child: const Text('Lançar na mesa'),
          ),
        ],
      ),
    );
  }
}
