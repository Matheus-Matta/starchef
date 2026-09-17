import 'package:flutter/material.dart';

import '../domain/product_options.dart';

class ProductThumbnail extends StatelessWidget {
  const ProductThumbnail({super.key, required this.product, this.size = 52});

  final Map<String, dynamic> product;
  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fallback = ColoredBox(
      color: scheme.surfaceContainerHighest,
      child: Center(
        child: Icon(
          Icons.restaurant_menu_outlined,
          color: scheme.onSurfaceVariant,
          size: size * .45,
        ),
      ),
    );
    final url = productImageUrl(product);
    final content = url.isEmpty
        ? fallback
        : Image.network(
            url,
            width: size,
            height: size,
            fit: BoxFit.cover,
            cacheWidth: (size * MediaQuery.devicePixelRatioOf(context)).round(),
            errorBuilder: (_, _, _) => fallback,
          );
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: SizedBox.square(dimension: size, child: content),
    );
  }
}
