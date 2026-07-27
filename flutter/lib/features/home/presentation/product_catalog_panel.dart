import 'package:flutter/material.dart';

class ProductCatalogPanel extends StatelessWidget {
  const ProductCatalogPanel({
    super.key,
    required this.products,
    required this.allProducts,
    required this.categories,
    required this.selectedCategory,
    required this.search,
    required this.money,
    required this.imageUrlFor,
    required this.onSearchChanged,
    required this.onCategoryChanged,
    required this.onProductPressed,
  });

  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> allProducts;
  final List<Map<String, dynamic>> categories;
  final String? selectedCategory;
  final String search;
  final String Function(dynamic) money;
  final String? Function(Map<String, dynamic>) imageUrlFor;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<String?> onCategoryChanged;
  final ValueChanged<Map<String, dynamic>> onProductPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final counts = <String, int>{};
    for (final product in allProducts) {
      final categoryId = '${product['category'] ?? ''}';
      if (categoryId.isNotEmpty) {
        counts.update(categoryId, (value) => value + 1, ifAbsent: () => 1);
      }
    }

    return ColoredBox(
      color: scheme.surfaceContainerLowest,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    onChanged: onSearchChanged,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search_rounded),
                      hintText: 'Buscar produto, código ou categoria...',
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Container(
                  height: 48,
                  padding: const EdgeInsets.symmetric(horizontal: 13),
                  decoration: BoxDecoration(
                    color: scheme.surface,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: scheme.outlineVariant),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.inventory_2_outlined,
                        size: 18,
                        color: scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 7),
                      Text(
                        '${products.length} itens',
                        style: TextStyle(
                          color: scheme.onSurfaceVariant,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            SizedBox(
              height: 70,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  _CategoryButton(
                    label: 'Todos',
                    count: allProducts.length,
                    icon: Icons.grid_view_rounded,
                    selected: selectedCategory == null,
                    onPressed: () => onCategoryChanged(null),
                  ),
                  ...categories.map((item) {
                    final id = '${item['id']}';
                    return _CategoryButton(
                      label: '${item['name']}',
                      count: counts[id] ?? 0,
                      icon: _categoryIcon('${item['name']}'),
                      selected: selectedCategory == id,
                      onPressed: () => onCategoryChanged(id),
                    );
                  }),
                ],
              ),
            ),
            const SizedBox(height: 14),
            Expanded(
              child: products.isEmpty
                  ? _EmptyCatalog(search: search)
                  : GridView.builder(
                      keyboardDismissBehavior:
                          ScrollViewKeyboardDismissBehavior.onDrag,
                      gridDelegate:
                          const SliverGridDelegateWithMaxCrossAxisExtent(
                            maxCrossAxisExtent: 244,
                            mainAxisExtent: 250,
                            crossAxisSpacing: 12,
                            mainAxisSpacing: 12,
                          ),
                      itemCount: products.length,
                      itemBuilder: (context, index) {
                        final product = products[index];
                        return _ProductCard(
                          product: product,
                          money: money,
                          imageUrl: imageUrlFor(product),
                          onPressed: () => onProductPressed(product),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  static IconData _categoryIcon(String name) {
    final normalized = name.toLowerCase();
    if (normalized.contains('beb') ||
        normalized.contains('drink') ||
        normalized.contains('suco')) {
      return Icons.local_drink_outlined;
    }
    if (normalized.contains('sobrem') ||
        normalized.contains('doce') ||
        normalized.contains('dessert')) {
      return Icons.icecream_outlined;
    }
    if (normalized.contains('lanche') ||
        normalized.contains('burger') ||
        normalized.contains('hamb')) {
      return Icons.lunch_dining_outlined;
    }
    if (normalized.contains('pizza')) return Icons.local_pizza_outlined;
    if (normalized.contains('café') || normalized.contains('cafe')) {
      return Icons.coffee_outlined;
    }
    return Icons.restaurant_outlined;
  }
}

class _CategoryButton extends StatelessWidget {
  const _CategoryButton({
    required this.label,
    required this.count,
    required this.icon,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final int count;
  final IconData icon;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(right: 9),
      child: Material(
        color: selected ? scheme.primaryContainer : scheme.surface,
        borderRadius: BorderRadius.circular(11),
        child: InkWell(
          onTap: onPressed,
          borderRadius: BorderRadius.circular(11),
          child: Container(
            constraints: const BoxConstraints(minWidth: 112),
            padding: const EdgeInsets.symmetric(horizontal: 13),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(11),
              border: Border.all(
                color: selected ? scheme.primary : scheme.outlineVariant,
                width: selected ? 1.5 : 1,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  icon,
                  size: 22,
                  color: selected ? scheme.primary : scheme.onSurfaceVariant,
                ),
                const SizedBox(width: 9),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 112),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                          color: selected
                              ? scheme.onPrimaryContainer
                              : scheme.onSurface,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '$count ${count == 1 ? 'item' : 'itens'}',
                        style: TextStyle(
                          color: scheme.onSurfaceVariant,
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({
    required this.product,
    required this.money,
    required this.imageUrl,
    required this.onPressed,
  });

  final Map<String, dynamic> product;
  final String Function(dynamic) money;
  final String? imageUrl;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final promotional = product['promotional_price'] != null;
    final weighed =
        product['pricing_unit'] == 'kg' || product['is_weighed'] == true;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onPressed,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              height: 116,
              width: double.infinity,
              child: _ProductImage(
                imageUrl: imageUrl,
                category: '${product['category_name'] ?? ''}',
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(13, 11, 11, 11),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${product['name']}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 13,
                        height: 1.18,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '${product['category_name'] ?? 'Sem categoria'}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Expanded(
                          child: Wrap(
                            crossAxisAlignment: WrapCrossAlignment.end,
                            spacing: 5,
                            children: [
                              Text(
                                money(product['current_price']),
                                style: TextStyle(
                                  color: scheme.primary,
                                  fontSize: 15,
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                              if (weighed)
                                Text(
                                  '/ kg',
                                  style: TextStyle(
                                    color: scheme.onSurfaceVariant,
                                    fontSize: 10,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              if (promotional &&
                                  product['sale_price'] !=
                                      product['promotional_price'])
                                Text(
                                  money(product['sale_price']),
                                  style: TextStyle(
                                    color: scheme.onSurfaceVariant,
                                    fontSize: 10,
                                    decoration: TextDecoration.lineThrough,
                                  ),
                                ),
                            ],
                          ),
                        ),
                        Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: scheme.primaryContainer,
                            borderRadius: BorderRadius.circular(9),
                          ),
                          child: Icon(
                            Icons.add_rounded,
                            size: 20,
                            color: scheme.primary,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProductImage extends StatelessWidget {
  const _ProductImage({required this.imageUrl, required this.category});

  final String? imageUrl;
  final String category;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fallback = ColoredBox(
      color: scheme.primaryContainer,
      child: Center(
        child: Icon(
          ProductCatalogPanel._categoryIcon(category),
          size: 40,
          color: scheme.primary.withValues(alpha: .72),
        ),
      ),
    );
    if (imageUrl == null) return fallback;
    return Image.network(
      imageUrl!,
      fit: BoxFit.cover,
      filterQuality: FilterQuality.medium,
      errorBuilder: (_, _, _) => fallback,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return Stack(
          fit: StackFit.expand,
          children: [
            fallback,
            Center(
              child: SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  value: progress.expectedTotalBytes == null
                      ? null
                      : progress.cumulativeBytesLoaded /
                            progress.expectedTotalBytes!,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _EmptyCatalog extends StatelessWidget {
  const _EmptyCatalog({required this.search});

  final String search;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 360),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              search.trim().isEmpty
                  ? Icons.inventory_2_outlined
                  : Icons.search_off_rounded,
              size: 48,
              color: scheme.onSurfaceVariant,
            ),
            const SizedBox(height: 12),
            Text(
              search.trim().isEmpty
                  ? 'Nenhum produto disponível'
                  : 'Nenhum produto encontrado',
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 5),
            Text(
              search.trim().isEmpty
                  ? 'Verifique o cardápio e a disponibilidade da unidade.'
                  : 'Tente buscar por outro nome, código ou categoria.',
              textAlign: TextAlign.center,
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
