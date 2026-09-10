import 'package:flutter/material.dart';

/// Resolve a foto de perfil nova, com compatibilidade para respostas antigas.
String productImageUrl(Map<String, dynamic> product) {
  final direct = '${product['logo_p'] ?? ''}'.trim();
  if (direct.isNotEmpty) return direct;
  return '${product['image'] ?? ''}'.trim();
}

class ProductProfileThumbnail extends StatelessWidget {
  const ProductProfileThumbnail({
    super.key,
    required this.product,
    this.size = 44,
  });

  final Map<String, dynamic> product;
  final double size;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final fallback = ColoredBox(
      color: scheme.surfaceContainer,
      child: Center(
        child: Icon(
          Icons.restaurant_menu_outlined,
          color: scheme.onSurfaceVariant,
          size: size * .48,
        ),
      ),
    );
    final url = productImageUrl(product);
    final image = url.isEmpty
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
      borderRadius: BorderRadius.circular(8),
      child: SizedBox.square(dimension: size, child: image),
    );
  }
}
