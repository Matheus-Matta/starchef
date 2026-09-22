import 'package:flutter/material.dart';

import '../data/order_draft_cart.dart';

/// De qual comanda veio este item, se veio de alguma.
///
/// A marca é posta por `OrderDraftCart.cartItems` ao juntar as anotações dos
/// cartões com o que o operador passou agora — ler a mesma chave é o que
/// evita duas verdades sobre o mesmo item.
Object? numeroDaComandaDoItem(Map<String, dynamic> item) {
  final texto = '${item[OrderDraftCart.marcaDaComanda] ?? ''}'.trim();
  return texto.isEmpty ? null : texto;
}

/// "Comanda 12" ao lado do produto, na linha do carrinho.
///
/// Numa conta com quatro comandas o carrinho é uma lista só. Sem dizer de qual
/// cartão é cada linha, ninguém sabe o que pertence a quem — e a conferência
/// em voz alta com o cliente ("quanto é a minha?") não fecha.
class CartCommandBadge extends StatelessWidget {
  const CartCommandBadge({super.key, required this.numero});

  final Object numero;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        color: scheme.primaryContainer.withValues(alpha: .55),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        'Comanda $numero',
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w800,
          color: scheme.onPrimaryContainer,
        ),
      ),
    );
  }
}
