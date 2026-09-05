import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

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

  /// Quantos produtos cada categoria tem, sem refazer a conta a cada build.
  ///
  /// O painel se reconstrói a cada tecla da busca e a cada mudança de estado
  /// da tela de vendas — e a contagem varria o catálogo INTEIRO em todas
  /// elas. A lista de produtos só é reatribuída quando o catálogo é
  /// recarregado (nunca alterada no lugar), então a identidade dela basta
  /// como chave: mesma lista, mesma conta.
  ///
  /// Um registro só é suficiente porque existe um catálogo por vez na tela.
  static List<Map<String, dynamic>>? _countedSource;
  static Map<String, int> _countedResult = const {};

  static Map<String, int> _categoryCounts(List<Map<String, dynamic>> products) {
    if (identical(products, _countedSource)) return _countedResult;
    final counts = <String, int>{};
    for (final product in products) {
      final categoryId = '${product['category'] ?? ''}';
      if (categoryId.isNotEmpty) {
        counts.update(categoryId, (value) => value + 1, ifAbsent: () => 1);
      }
    }
    _countedSource = products;
    _countedResult = counts;
    return counts;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final counts = _categoryCounts(allProducts);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: AppTheme.radius,
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 520;
          final searchField = TextField(
            onChanged: onSearchChanged,
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search_rounded),
              hintText: 'Buscar produto, código ou categoria...',
            ),
          );
          final totalBadge = ShadBadge.outline(
            shape: const RoundedRectangleBorder(borderRadius: AppTheme.radius),
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 10),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.inventory_2_outlined,
                  size: 16,
                  color: scheme.onSurfaceVariant,
                ),
                const SizedBox(width: 6),
                Text(
                  '${products.length} itens',
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
          );
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 15, 16, 12),
                child: compact
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          searchField,
                          const SizedBox(height: 8),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: totalBadge,
                          ),
                        ],
                      )
                    : Row(
                        children: [
                          Expanded(child: searchField),
                          const SizedBox(width: 10),
                          totalBadge,
                        ],
                      ),
              ),
              Divider(height: 1, color: scheme.outlineVariant),
              SizedBox(
                height: 44,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 6,
                  ),
                  children: [
                    _CategoryButton(
                      label: 'Todos',
                      count: allProducts.length,
                      selected: selectedCategory == null,
                      onPressed: () => onCategoryChanged(null),
                    ),
                    for (final item in categories) ...[
                      const SizedBox(width: 7),
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
                    ? _EmptyCatalog(search: search)
                    : GridView.builder(
                        padding: const EdgeInsets.all(10),
                        keyboardDismissBehavior:
                            ScrollViewKeyboardDismissBehavior.onDrag,
                        gridDelegate:
                            const SliverGridDelegateWithMaxCrossAxisExtent(
                              // O card encolheu junto com o resto: cabe
                              // mais produto por tela sem o operador rolar.
                              // A altura tem folga de propósito — o nome usa
                              // até duas linhas, e é o pior caso que decide.
                              maxCrossAxisExtent: 200,
                              mainAxisExtent: 190,
                              crossAxisSpacing: 8,
                              mainAxisSpacing: 8,
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
          );
        },
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
  Widget build(BuildContext context) => ShadButton.raw(
    variant: selected ? ShadButtonVariant.primary : ShadButtonVariant.outline,
    onPressed: onPressed,
    height: AppTheme.controlHeight,
    padding: const EdgeInsets.symmetric(horizontal: 10),
    leading: Icon(
      selected ? Icons.check_rounded : Icons.restaurant_menu_outlined,
      size: 15,
    ),
    child: Text(
      '$label · $count',
      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
    ),
  );
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
    final imageUrl = '${product['image'] ?? ''}'.trim();

    return ShadCard(
      padding: EdgeInsets.zero,
      radius: AppTheme.radius,
      shadows: const [],
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      child: Material(
        color: Colors.transparent,
        clipBehavior: Clip.antiAlias,
        shape: const RoundedRectangleBorder(borderRadius: AppTheme.radius),
        child: InkWell(
          onTap: onPressed,
          borderRadius: AppTheme.radius,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SizedBox(
                height: 76,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    _ProductImage(url: imageUrl),
                    if (promotional || weighed)
                      Positioned(
                        top: 7,
                        left: 7,
                        child: ShadBadge.raw(
                          variant: ShadBadgeVariant.secondary,
                          backgroundColor: scheme.surface.withValues(
                            alpha: .92,
                          ),
                          foregroundColor: scheme.onSurface,
                          shape: const RoundedRectangleBorder(
                            borderRadius: AppTheme.radius,
                          ),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 7,
                            vertical: 4,
                          ),
                          child: Text(
                            promotional ? 'OFERTA' : 'POR KG',
                            style: const TextStyle(
                              fontSize: 8,
                              fontWeight: FontWeight.w900,
                              letterSpacing: .5,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(9, 7, 7, 7),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // O CÓDIGO SAIU DE DENTRO DO NOME.
                      //
                      // Ele vinha como prefixo do título, no mesmo corpo e no
                      // mesmo peso: comia a primeira linha do nome — que só
                      // tem duas — e num produto de nome longo o que sobrava
                      // na tela era o número e reticências. Agora fica na
                      // linha de cima da categoria, no tamanho dela.
                      Text(
                        '${product['name']}',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.15,
                          fontWeight: FontWeight.w800,
                          color: scheme.onSurface,
                        ),
                      ),
                      const SizedBox(height: 3),
                      if (code.isNotEmpty)
                        Text(
                          '#$code',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontSize: 9,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      Text(
                        '${product['category_name'] ?? 'Sem categoria'}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: scheme.onSurfaceVariant,
                          fontSize: 9,
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
                              spacing: 4,
                              children: [
                                Text(
                                  money(product['current_price']),
                                  style: TextStyle(
                                    color: scheme.primary,
                                    fontSize: 14,
                                    fontWeight: FontWeight.w900,
                                  ),
                                ),
                                if (weighed)
                                  Text(
                                    '/ kg',
                                    style: TextStyle(
                                      color: scheme.onSurfaceVariant,
                                      fontSize: 9,
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
                                      fontSize: 9,
                                      decoration: TextDecoration.lineThrough,
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          Container(
                            width: 30,
                            height: 30,
                            decoration: BoxDecoration(
                              color: scheme.primary,
                              borderRadius: AppTheme.radius,
                            ),
                            child: const Icon(
                              Icons.add_rounded,
                              size: 18,
                              color: Colors.white,
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
      ),
    );
  }
}

class _ProductImage extends StatelessWidget {
  const _ProductImage({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fallback = ColoredBox(
      color: scheme.surfaceContainer,
      child: Center(
        child: Icon(
          Icons.restaurant_menu_outlined,
          size: 30,
          color: scheme.onSurfaceVariant.withValues(alpha: .7),
        ),
      ),
    );
    if (url.isEmpty) return fallback;
    // A imagem é DECODIFICADA no tamanho do card, não no tamanho do arquivo.
    //
    // Sem `cacheWidth`/`cacheHeight`, uma foto de 2000x1500 do cardápio ocupa
    // ~12 MB de bitmap na memória para aparecer num quadro de 88px de altura —
    // e o catálogo desenha dezenas deles ao mesmo tempo. O pixel ratio entra
    // na conta para a foto continuar nítida numa tela HiDPI.
    //
    // Só muda o custo: a mesma URL, o mesmo `BoxFit.cover`, o mesmo fallback.
    return LayoutBuilder(
      builder: (context, constraints) {
        final ratio = MediaQuery.devicePixelRatioOf(context);
        int? cache(double side) =>
            side.isFinite && side > 0 ? (side * ratio).round() : null;
        return Image.network(
          url,
          fit: BoxFit.cover,
          filterQuality: FilterQuality.medium,
          cacheWidth: cache(constraints.maxWidth),
          cacheHeight: cache(constraints.maxHeight),
          errorBuilder: (_, _, _) => fallback,
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
    return AppEmptyState(
      icon: search.trim().isEmpty
          ? Icons.inventory_2_outlined
          : Icons.search_off_rounded,
      title: search.trim().isEmpty
          ? 'Nenhum produto disponível'
          : 'Nenhum produto encontrado',
      description: search.trim().isEmpty
          ? 'Verifique o cardápio e a disponibilidade da unidade.'
          : 'Tente buscar por outro nome, código ou categoria.',
    );
  }
}
