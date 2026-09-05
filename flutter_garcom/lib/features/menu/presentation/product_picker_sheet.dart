import 'package:flutter/material.dart';

import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/paginated_picker.dart';
import '../../../core/widgets/picker_tile.dart';
import '../../orders/data/orders_repository.dart';
import '../../orders/presentation/order_formatters.dart';
import '../domain/product_options.dart';
import 'product_config_view.dart';

export '../domain/product_options.dart' show ProductChoice;

/// Busca do catálogo (paginada) e, na sequência, a configuração do item.
///
/// Duas etapas na mesma folha: escolher o produto e dizer como ele vai. A
/// altura é fixa de propósito — a lista carrega páginas conforme o garçom
/// rola, e uma folha que cresce a cada página "pula" debaixo do dedo.
Future<ProductChoice?> showProductPicker(
  BuildContext context,
  OrdersRepository repository,
) => showAppSheet<ProductChoice>(
  context,
  heightFactor: .85,
  builder: (context) => _ProductPicker(repository: repository),
);

class _ProductPicker extends StatefulWidget {
  const _ProductPicker({required this.repository});

  final OrdersRepository repository;

  @override
  State<_ProductPicker> createState() => _ProductPickerState();
}

class _ProductPickerState extends State<_ProductPicker> {
  Map<String, dynamic>? _selected;

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    if (selected != null) {
      return ProductConfigView(
        product: selected,
        onBack: () => setState(() => _selected = null),
        onConfirm: (choice) => Navigator.of(context).pop(choice),
      );
    }
    return Column(
      children: [
        const AppSheetHeader(title: 'Adicionar item'),
        Expanded(
          child: PaginatedPicker(
            searchHint: 'Buscar produto',
            emptyMessage: 'Nenhum produto encontrado.',
            fetch: _fetch,
            itemBuilder: (context, product) => PickerTile(
              title: '${product['name'] ?? ''}',
              subtitle: _subtitle(product),
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
  }

  /// O filtro é aplicado sobre a página recebida: `hasMore` continua vindo da
  /// API, então a rolagem segue buscando mesmo quando uma página inteira cai
  /// fora (só adicionais, por exemplo).
  Future<ResourcePage> _fetch(int page, String search) async {
    final result = await widget.repository.products(page: page, search: search);
    return ResourcePage(
      rows: result.rows.where(isSellable).toList(),
      hasMore: result.hasMore,
    );
  }

  static String? _subtitle(Map<String, dynamic> product) {
    final code = fieldText(product['internal_code']);
    final options =
        activeVariations(product).length + activeAddons(product).length;
    final parts = [
      if (code.isNotEmpty) '#$code',
      if (options > 0) '$options opção${options == 1 ? '' : 'ões'}',
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }
}
