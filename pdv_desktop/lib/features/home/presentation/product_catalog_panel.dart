import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import 'product_card_metrics.dart';
import 'product_catalog_tile.dart';

class ProductCatalogPanel extends StatelessWidget {
  const ProductCatalogPanel({
    super.key,
    required this.products,
    required this.allProducts,
    required this.categories,
    required this.selectedCategory,
    required this.search,
    required this.money,
    required this.onSearchChanged,
    required this.onCategoryChanged,
    required this.onProductPressed,
    this.searchFocusNode,
  });

  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> allProducts;
  final List<Map<String, dynamic>> categories;
  final String? selectedCategory;
  final String search;
  final String Function(dynamic) money;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<String?> onCategoryChanged;
  final ValueChanged<Map<String, dynamic>> onProductPressed;
  final FocusNode? searchFocusNode;

  Map<String, int> get _categoryCounts {
    final result = <String, int>{};
    for (final product in allProducts) {
      final id = '${product['category'] ?? ''}';
      if (id.isNotEmpty) result.update(id, (n) => n + 1, ifAbsent: () => 1);
    }
    return result;
  }

  bool _available(Map<String, dynamic> product) =>
      product['is_active'] != false &&
      product['available'] != false &&
      product['is_available'] != false;

  Map<String, dynamic>? get _firstAvailable {
    for (final product in products) {
      if (_available(product)) return product;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final counts = _categoryCounts;
    final firstAvailable = _firstAvailable;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: AppTheme.radius,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    focusNode: searchFocusNode,
                    onChanged: onSearchChanged,
                    onSubmitted: (_) {
                      if (firstAvailable != null) {
                        onProductPressed(firstAvailable);
                      }
                    },
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search_rounded),
                      hintText: 'Buscar produto, código ou categoria',
                      suffixIcon: _SearchShortcut(),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  '${products.length} produtos',
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          Divider(height: 1, color: scheme.outlineVariant),
          SizedBox(
            height: 43,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
              children: [
                _CategoryButton(
                  label: 'Todos',
                  count: allProducts.length,
                  selected: selectedCategory == null,
                  onPressed: () => onCategoryChanged(null),
                ),
                for (final item in categories) ...[
                  const SizedBox(width: 6),
                  _CategoryButton(
                    label: '${item['name']}',
                    count: counts['${item['id']}'] ?? 0,
                    selected: selectedCategory == '${item['id']}',
                    onPressed: () => onCategoryChanged('${item['id']}'),
                  ),
                ],
              ],
            ),
          ),
          Divider(height: 1, color: scheme.outlineVariant),
          Expanded(
            child: products.isEmpty
                ? ProductCatalogEmptyState(search: search)
                : GridView.builder(
                    padding: const EdgeInsets.all(8),
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
                    gridDelegate:
                        const SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: ProductCardMetrics.maxCardWidth,
                          mainAxisExtent: ProductCardMetrics.cardHeight,
                          crossAxisSpacing: ProductCardMetrics.spacing,
                          mainAxisSpacing: ProductCardMetrics.spacing,
                        ),
                    itemCount: products.length,
                    itemBuilder: (_, index) => ProductCatalogTile(
                      product: products[index],
                      money: money,
                      onPressed: () => onProductPressed(products[index]),
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _SearchShortcut extends StatelessWidget {
  const _SearchShortcut();

  @override
  Widget build(BuildContext context) => Center(
    widthFactor: 1,
    child: Text(
      'F2  /',
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: 11,
        fontWeight: FontWeight.w800,
      ),
    ),
  );
}

class _CategoryButton extends StatelessWidget {
  const _CategoryButton({
    required this.label,
    required this.count,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final int count;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 32,
    child: selected
        ? FilledButton(onPressed: onPressed, child: Text('$label · $count'))
        : OutlinedButton(onPressed: onPressed, child: Text('$label · $count')),
  );
}
