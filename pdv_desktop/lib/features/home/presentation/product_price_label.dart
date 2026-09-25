import 'package:flutter/material.dart';

/// O preço do produto na grade, com o "de" riscado quando há promoção.
///
/// O RISCADO NÃO É ENFEITE. O caixa precisa saber que aquele preço menor é
/// deliberado: sem o "de", um produto que amanhece a R$ 15 em vez de R$ 20
/// parece erro de cadastro, e o operador liga para o escritório para confirmar
/// antes de vender — na frente do cliente.
///
/// Também é o que permite responder à pergunta que o cliente faz quando vê o
/// cartaz: "não era vinte?". Era. Hoje é quinze.
class ProductPriceLabel extends StatelessWidget {
  const ProductPriceLabel({
    super.key,
    required this.product,
    required this.money,
    this.suffix = '',
    this.fontSize = 17,
  });

  final Map<String, dynamic> product;
  final String Function(dynamic) money;

  /// " / kg" nos pesáveis. Fica de fora do riscado: o "de" já é um número.
  final String suffix;
  final double fontSize;

  /// O valor cheio a exibir riscado, ou `null` quando não há nada a riscar.
  ///
  /// Vem do SERVIDOR (`compare_at_price`). Calcular aqui — comparando
  /// `sale_price` com `current_price` — daria a resposta errada no caso que
  /// mais importa: o encarte pode anunciar "de 30 por 15" num produto
  /// cadastrado a 20, e o terminal não tem como saber disso sozinho.
  double? get _riscado {
    final bruto = product['compare_at_price'];
    if (bruto == null) return null;
    final valor = bruto is num ? bruto.toDouble() : double.tryParse('$bruto');
    if (valor == null || valor <= 0) return null;
    final atual = _numero(product['current_price']);
    return valor > atual ? valor : null;
  }

  static double _numero(dynamic bruto) {
    if (bruto is num) return bruto.toDouble();
    return double.tryParse('$bruto') ?? 0;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final cheio = _riscado;
    final preco = Text(
      '${money(product['current_price'])}$suffix',
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
      style: TextStyle(
        color: cheio == null ? scheme.primary : scheme.tertiary,
        fontSize: fontSize,
        fontWeight: FontWeight.w900,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
    );
    if (cheio == null) return preco;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          money(cheio),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: scheme.onSurfaceVariant,
            fontSize: fontSize - 6,
            decoration: TextDecoration.lineThrough,
            fontFeatures: const [FontFeature.tabularFigures()],
          ),
        ),
        preco,
      ],
    );
  }
}
