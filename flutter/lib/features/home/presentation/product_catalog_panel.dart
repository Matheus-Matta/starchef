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
            // Busca e filtro lado a lado, como no frontend web. A faixa
            // horizontal de categorias saiu: com muitas categorias ela exigia
            // rolagem lateral para achar a última, e ocupava 70 px de altura
            // que agora são do cardápio.
            Row(
              children: [
                Expanded(
                  flex: 3,
                  child: TextField(
                    onChanged: onSearchChanged,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search_rounded),
                      hintText: 'Buscar produto, código ou categoria...',
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  flex: 2,
                  child: DropdownButtonFormField<String?>(
                    key: ValueKey(
                      'category-$selectedCategory-${categories.length}',
                    ),
                    initialValue: selectedCategory,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.filter_list_rounded),
                    ),
                    items: [
                      DropdownMenuItem(
                        value: null,
                        child: Text(
                          'Todas as categorias · ${allProducts.length}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      ...categories.map((item) {
                        final id = '${item['id']}';
                        return DropdownMenuItem(
                          value: id,
                          child: Text(
                            '${item['name']} · ${counts[id] ?? 0}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        );
                      }),
                    ],
                    onChanged: onCategoryChanged,
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
            Expanded(
              child: products.isEmpty
                  ? _EmptyCatalog(search: search)
                  : GridView.builder(
                      keyboardDismissBehavior:
                          ScrollViewKeyboardDismissBehavior.onDrag,
                      gridDelegate:
                          const SliverGridDelegateWithMaxCrossAxisExtent(
                            maxCrossAxisExtent: 244,
                            mainAxisExtent: 120,
                            crossAxisSpacing: 12,
                            mainAxisSpacing: 12,
                          ),
                      itemCount: products.length,
                      itemBuilder: (context, index) {
                        final product = products[index];
                        return _ProductCard(
                          product: product,
                          money: money,
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
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({
    required this.product,
    required this.money,
    required this.onPressed,
  });

  final Map<String, dynamic> product;
  final String Function(dynamic) money;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final promotional = product['promotional_price'] != null;
    final weighed =
        product['pricing_unit'] == 'kg' || product['is_weighed'] == true;
    final code = '${product['internal_code'] ?? ''}'.trim();

    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onPressed,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 10, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text.rich(
                TextSpan(
                  style: TextStyle(
                    fontSize: 13,
                    height: 1.18,
                    fontWeight: FontWeight.w800,
                    color: scheme.onSurface,
                  ),
                  children: [
                    if (code.isNotEmpty)
                      TextSpan(
                        text: '#$code  ',
                        style: TextStyle(color: scheme.onSurfaceVariant),
                      ),
                    TextSpan(text: '${product['name']}'),
                  ],
                ),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 4),
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
              const Spacer(),
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
