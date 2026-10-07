import 'package:flutter/material.dart';

import '../domain/product_options.dart';

/// Produto sem variação nem adicional: não há o que configurar, entra com um
/// toque (como no PDV desktop). Segurar ainda abre a configuração.
bool entraComUmToque(Map<String, dynamic> product) =>
    activeVariations(product).isEmpty && activeAddons(product).isEmpty;

ProductChoice escolhaSimples(Map<String, dynamic> product) => ProductChoice(
  productId: '${product['id']}',
  productName: '${product['name'] ?? ''}',
  quantity: 1,
);

/// Confirmação curta: o garçom vê que entrou sem sair do cardápio.
void avisarAdicionado(BuildContext context, ProductChoice choice) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text('${choice.quantity}× ${choice.productName} adicionado'),
        duration: const Duration(milliseconds: 1200),
      ),
    );
}
