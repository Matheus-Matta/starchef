import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/paginated_picker.dart';
import '../../orders/data/orders_repository.dart';
import '../../orders/presentation/order_formatters.dart';

/// O que o garçom escolheu lançar no pedido.
class ProductChoice {
  const ProductChoice({
    required this.productId,
    required this.productName,
    required this.quantity,
    this.variationId,
    this.addonIds = const [],
    this.note = '',
  });

  final String productId;
  final String productName;
  final int quantity;
  final String? variationId;
  final List<String> addonIds;
  final String note;
}

/// Busca do catálogo (paginada) e, na sequência, variação, adicionais,
/// quantidade e observação — mesma pergunta que o PDV desktop faz
/// (`product_config_dialog.dart`), só que numa folha em vez de um diálogo.
Future<ProductChoice?> showProductPicker(
  BuildContext context,
  OrdersRepository repository,
) => showModalBottomSheet<ProductChoice>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => Padding(
    padding: EdgeInsets.only(
      bottom: MediaQuery.of(context).viewInsets.bottom,
    ),
    child: SizedBox(
      height: MediaQuery.of(context).size.height * .85,
      child: _ProductPicker(repository: repository),
    ),
  ),
);

class _ProductPicker extends StatefulWidget {
  const _ProductPicker({required this.repository});

  final OrdersRepository repository;

  @override
  State<_ProductPicker> createState() => _ProductPickerState();
}

class _ProductPickerState extends State<_ProductPicker> {
  Map<String, dynamic>? _selected;

  /// Adicional e insumo não são vendidos sozinhos, e produto por kilo depende
  /// da balança do balcão — nenhum dos três cabe no lançamento pelo celular.
  static bool _sellable(Map<String, dynamic> product) =>
      product['product_type'] != 'addon' &&
      product['product_type'] != 'input' &&
      product['pricing_unit'] != 'kg';

  @override
  Widget build(BuildContext context) =>
      _selected == null ? _buildList() : _ProductConfig(
        product: _selected!,
        onBack: () => setState(() => _selected = null),
      );

  Widget _buildList() => Column(
    children: [
      const Padding(
        padding: EdgeInsets.fromLTRB(20, 0, 20, 12),
        child: Align(
          alignment: Alignment.centerLeft,
          child: Text(
            'Adicionar item',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
        ),
      ),
      Expanded(
        child: PaginatedPicker(
          searchHint: 'Buscar produto',
          emptyMessage: 'Nenhum produto encontrado.',
          fetch: (page, search) async {
            final result = await widget.repository.products(
              page: page,
              search: search,
            );
            // O filtro é aplicado sobre a página recebida: `hasMore` continua
            // vindo da API, então a rolagem segue buscando mesmo quando uma
            // página inteira cai fora (só adicionais, por exemplo).
            return (
              rows: result.rows.where(_sellable).toList(),
              hasMore: result.hasMore,
            );
          },
          itemBuilder: (context, product) => PickerTile(
            title: '${product['name'] ?? ''}',
            subtitle: _pickerSubtitle(product),
            trailing: Text(
              money(product['sale_price']),
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            onTap: () => setState(() => _selected = product),
          ),
        ),
      ),
    ],
  );

  static String? _pickerSubtitle(Map<String, dynamic> product) {
    final code = '${product['internal_code'] ?? ''}'.trim();
    final opcoes = _activeVariations(product).length + _activeAddons(product).length;
    final partes = [
      if (code.isNotEmpty) '#$code',
      if (opcoes > 0) '$opcoes opção${opcoes == 1 ? '' : 'ões'}',
    ];
    return partes.isEmpty ? null : partes.join(' · ');
  }
}

/// Variações/adicionais ativos do produto — mesmo filtro do PDV
/// (`product_config_dialog.dart`): o cadastro pode ter itens desativados sem
/// removê-los do histórico de pedidos antigos.
List<Map<String, dynamic>> _activeVariations(Map<String, dynamic> product) =>
    (product['variations'] as List? ?? const [])
        .whereType<Map>()
        .map(Map<String, dynamic>.from)
        .where((item) => item['is_active'] != false)
        .toList();

List<Map<String, dynamic>> _activeAddons(Map<String, dynamic> product) =>
    (product['addons'] as List? ?? const [])
        .whereType<Map>()
        .map(Map<String, dynamic>.from)
        .where((item) => item['is_active'] != false)
        .toList();

class _ProductConfig extends StatefulWidget {
  const _ProductConfig({required this.product, required this.onBack});

  final Map<String, dynamic> product;
  final VoidCallback onBack;

  @override
  State<_ProductConfig> createState() => _ProductConfigState();
}

class _ProductConfigState extends State<_ProductConfig> {
  final _note = TextEditingController();
  int _quantity = 1;
  String? _variationId;
  final Set<String> _selectedAddons = {};

  late final List<Map<String, dynamic>> _variations = _activeVariations(
    widget.product,
  );
  late final List<Map<String, dynamic>> _addons = _activeAddons(
    widget.product,
  );

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  double get _unitPrice => expectedUnitPrice(
    widget.product,
    variationId: _variationId,
    addonIds: _selectedAddons,
  );

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final product = widget.product;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              IconButton(
                onPressed: widget.onBack,
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
          if (_variations.isNotEmpty) ...[
            const SizedBox(height: 18),
            const _SectionLabel('Variação'),
            RadioGroup<String>(
              groupValue: _variationId,
              onChanged: (value) => setState(() => _variationId = value),
              child: Column(
                children: _variations
                    .map(
                      (item) => RadioListTile<String>(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        value: '${item['id']}',
                        title: Text('${item['name']}'),
                        secondary: Text(
                          '+ ${money(item['price_delta'])}',
                          style: TextStyle(color: scheme.onSurfaceVariant),
                        ),
                      ),
                    )
                    .toList(),
              ),
            ),
          ],
          if (_addons.isNotEmpty) ...[
            const SizedBox(height: 8),
            const _SectionLabel('Adicionais'),
            ..._addons.map(
              (item) => CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                controlAffinity: ListTileControlAffinity.leading,
                value: _selectedAddons.contains('${item['id']}'),
                onChanged: (checked) => setState(() {
                  final id = '${item['id']}';
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
              ),
            ),
          ],
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
            'Total do item: ${money(_unitPrice * _quantity)}',
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
                productName: '${product['name'] ?? ''}',
                quantity: _quantity,
                variationId: _variationId,
                addonIds: _selectedAddons.toList(),
                note: _note.text.trim(),
              ),
            ),
            child: const Text('Lançar no pedido'),
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

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
