import 'package:flutter/material.dart';

import '../../orders/presentation/order_formatters.dart';

/// O preço do produto na tela do garçom, com o "de" riscado quando há promoção.
///
/// O GARÇOM É QUEM RESPONDE AO CLIENTE. Ele está em pé na mesa quando alguém
/// pergunta "não era vinte?", e sem o riscado ele não tem como saber se o
/// quinze na tela é promoção ou erro — a saída dele é ir até o caixa perguntar,
/// deixando a mesa esperando.
///
/// O valor cheio vem do SERVIDOR (`compare_at_price`). Deduzir aqui,
/// comparando o cadastrado com o cobrado, erraria no caso que mais importa: o
/// encarte pode anunciar "de 30 por 15" num produto cadastrado a 20, e o
/// aparelho não tem como saber disso sozinho.
class ProductPriceText extends StatelessWidget {
  const ProductPriceText({super.key, required this.product, this.fontSize = 14});

  final Map<String, dynamic> product;
  final double fontSize;

  double get _cobrado => amount(product['current_price'] ?? product['sale_price']);

  double? get _riscado {
    final bruto = product['compare_at_price'];
    if (bruto == null) return null;
    final valor = amount(bruto);
    return valor > _cobrado ? valor : null;
  }

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    final cheio = _riscado;
    final preco = Text(
      money(_cobrado),
      style: TextStyle(
        fontWeight: FontWeight.w700,
        fontSize: fontSize,
        color: cheio == null ? null : cores.tertiary,
      ),
    );
    if (cheio == null) return preco;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          money(cheio),
          style: TextStyle(
            fontSize: fontSize - 3,
            color: cores.onSurfaceVariant,
            decoration: TextDecoration.lineThrough,
          ),
        ),
        preco,
      ],
    );
  }
}
