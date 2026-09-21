import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/product_image_url.dart';
import '../../../core/widgets/shadcn_layout.dart';
import 'product_card_metrics.dart';

class ProductCatalogTile extends StatelessWidget {
  const ProductCatalogTile({
    super.key,
    required this.product,
    required this.money,
    required this.onPressed,
  });

  final Map<String, dynamic> product;
  final String Function(dynamic) money;
  final VoidCallback onPressed;

  bool get _available =>
      product['is_active'] != false &&
      product['available'] != false &&
      product['is_available'] != false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final weighed =
        product['pricing_unit'] == 'kg' || product['is_weighed'] == true;
    final code = '${product['internal_code'] ?? ''}'.trim();
    return Semantics(
      button: true,
      enabled: _available,
      label: '${product['name']}, ${money(product['current_price'])}',
      child: Material(
        color: scheme.surface,
        shape: RoundedRectangleBorder(
          borderRadius: AppTheme.radius,
          side: BorderSide(color: scheme.outlineVariant),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          canRequestFocus: _available,
          onTap: _available ? onPressed : null,
          focusColor: scheme.primaryContainer.withValues(alpha: .5),
          child: Opacity(
            opacity: _available ? 1 : .58,
            child: Row(
              children: [
                SizedBox(
                  width: ProductCardMetrics.cardHeight - 2,
                  height: ProductCardMetrics.cardHeight - 2,
                  child: _ProductImage(url: productImageUrl(product)),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(10, 9, 10, 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${product['name']}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 14,
                            height: 1.15,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          [
                            if (code.isNotEmpty) '#$code',
                            '${product['category_name'] ?? 'Sem categoria'}',
                          ].join(' · '),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontSize: 11,
                          ),
                        ),
                        const Spacer(),
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${money(product['current_price'])}${weighed ? ' / kg' : ''}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: scheme.primary,
                                  fontSize: 17,
                                  fontWeight: FontWeight.w900,
                                  fontFeatures: const [
                                    FontFeature.tabularFigures(),
                                  ],
                                ),
                              ),
                            ),
                            if (!_available)
                              Text(
                                'Indisponível',
                                style: TextStyle(
                                  color: scheme.error,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w800,
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
      child: Icon(
        Icons.restaurant_menu_outlined,
        color: scheme.onSurfaceVariant,
      ),
    );
    if (url.isEmpty) return fallback;
    return LayoutBuilder(
      builder: (_, constraints) {
        final ratio = MediaQuery.devicePixelRatioOf(context);
        final side = math.max(constraints.maxWidth, constraints.maxHeight);
        return Image.network(
          url,
          fit: BoxFit.cover,
          cacheWidth: side.isFinite ? (side * ratio).round() : null,
          errorBuilder: (_, _, _) => fallback,
        );
      },
    );
  }
}

class ProductCatalogEmptyState extends StatelessWidget {
  const ProductCatalogEmptyState({super.key, required this.search});

  final String search;

  @override
  Widget build(BuildContext context) => AppEmptyState(
    icon: search.trim().isEmpty
        ? Icons.inventory_2_outlined
        : Icons.search_off_rounded,
    title: search.trim().isEmpty
        ? 'Nenhum produto disponível'
        : 'Nenhum produto encontrado',
    description: search.trim().isEmpty
        ? 'Verifique o cardápio e a disponibilidade da unidade.'
        : 'Tente outro nome, código ou categoria.',
  );
}
