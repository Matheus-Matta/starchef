import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import 'atalho_da_busca.dart';
import 'grade_de_produtos.dart';
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
    this.destacado,
    this.onColunas,
    this.carregandoMais = false,
    this.searchFocusNode,
    this.searchGeneration = 0,
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

  /// O produto das setas e quantas colunas a grade tem (`GradeDeProdutos`).
  final int? destacado;
  final ValueChanged<int>? onColunas;

  /// O resto do cardápio ainda está chegando (`produtos_em_paginas.dart`).
  final bool carregandoMais;
  final FocusNode? searchFocusNode;

  /// Muda a cada venda nova: o campo é recriado vazio (ver `_resetToNewSale`).
  final int searchGeneration;

  Map<String, int> get _categoryCounts {
    final result = <String, int>{};
    for (final product in allProducts) {
      final id = '${product['category'] ?? ''}';
      if (id.isNotEmpty) result.update(id, (n) => n + 1, ifAbsent: () => 1);
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final counts = _categoryCounts;
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
                    key: ValueKey('catalog-search-$searchGeneration'),
                    focusNode: searchFocusNode,
                    onChanged: onSearchChanged,
                    // Enter CONCLUI a busca: o cursor sai do campo e as setas,
                    // o Espaço e o Enter voltam a ser da venda.
                    onSubmitted: (_) => searchFocusNode?.unfocus(),
                    decoration: const InputDecoration(
                      prefixIcon: Icon(Icons.search_rounded),
                      hintText: 'Buscar produto, código ou categoria',
                      suffixIcon: AtalhoDaBusca(),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  carregandoMais
                      ? '${products.length} produtos · carregando mais…'
                      : '${products.length} produtos',
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
                : GradeDeProdutos(
                    products: products,
                    money: money,
                    onProductPressed: onProductPressed,
                    destacado: destacado,
                    onColunas: onColunas,
                  ),
          ),
        ],
      ),
    );
  }
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
