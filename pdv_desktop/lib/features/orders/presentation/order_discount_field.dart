import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/formatters/decimal_money.dart';

/// Desconto do pedido digitado direto no resumo, sem diálogo.
///
/// Cada dígito entra pelos centavos, como no teclado de pagamento: "5", "50",
/// "500" vira R$ 0,05, R$ 0,50, R$ 5,00. O valor não vai ao servidor a cada
/// tecla — sobe junto do fechamento, que é quem grava (e confere a permissão).

/// "R$ 1.234,50" / "1234,5" / "abc" -> centavos, só pelos dígitos.
int centavosDigitados(String texto) {
  final digitos = texto.replaceAll(RegExp(r'\D'), '');
  if (digitos.isEmpty) return 0;
  // Teto de R$ 9.999.999,99: mais que isso é tecla presa, não desconto.
  final corte = digitos.length > 9
      ? digitos.substring(digitos.length - 9)
      : digitos;
  return int.parse(corte);
}

/// 123450 -> "1.234,50".
String formatarCentavos(int centavos) {
  final reais = (centavos ~/ 100).toString().replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  return '$reais,${(centavos % 100).toString().padLeft(2, '0')}';
}

/// 123450 -> "1234.50", o formato que a API recebe (sem ponto flutuante).
String centavosParaApi(int centavos) =>
    '${centavos ~/ 100}.${(centavos % 100).toString().padLeft(2, '0')}';

int centavosDe(Object? valor) => DecimalMoney.minorUnits(valor);

/// O desconto que o campo mostra: o digitado, ou o que o pedido já tem.
int descontoNaTela(Map<String, dynamic>? pedido, int? digitado) =>
    digitado ?? centavosDe(pedido?['discount']);

/// O total do servidor trocando o desconto gravado pelo digitado — o caixa vê
/// na hora o que vai cobrar, antes de o fechamento gravar. Nunca negativo.
double totalComDesconto(
  Map<String, dynamic>? pedido,
  double? totalDoRascunho,
  int? digitado,
) {
  final base = centavosDe(pedido?['total'] ?? totalDoRascunho);
  final total =
      base + centavosDe(pedido?['discount']) - descontoNaTela(pedido, digitado);
  return DecimalMoney.asNumber(total < 0 ? 0 : total);
}

class _CentavosFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue antigo,
    TextEditingValue novo,
  ) {
    final texto = formatarCentavos(centavosDigitados(novo.text));
    return TextEditingValue(
      text: texto,
      selection: TextSelection.collapsed(offset: texto.length),
    );
  }
}

/// O desconto digitado e o pedido a que ele pertence.
///
/// Preso ao pedido de propósito: abrir OUTRO pedido não pode carregar o
/// desconto do anterior. O rascunho tem a chave `draft`, e o fechamento lê o
/// valor ANTES de o rascunho virar pedido (e trocar de chave).
class TypedDiscount {
  String? _chave;
  int? _centavos;

  int? valorDe(String? chave) =>
      chave != null && chave == _chave ? _centavos : null;

  void definir(String? chave, int centavos) {
    _chave = chave;
    _centavos = centavos;
  }

  void limpar() {
    _chave = null;
    _centavos = null;
  }
}

class OrderDiscountField extends StatefulWidget {
  const OrderDiscountField({
    super.key,
    required this.cents,
    required this.maxCents,
    required this.onChanged,
  });

  final int cents;

  /// O subtotal: dar a mercadoria inteira é o teto (o servidor recusa acima).
  final int maxCents;
  final ValueChanged<int> onChanged;

  @override
  State<OrderDiscountField> createState() => _OrderDiscountFieldState();
}

class _OrderDiscountFieldState extends State<OrderDiscountField> {
  late final _controle = TextEditingController(
    text: formatarCentavos(widget.cents),
  );

  @override
  void didUpdateWidget(OrderDiscountField antigo) {
    super.didUpdateWidget(antigo);
    // Venda nova ou outro pedido: o campo acompanha o valor de fora.
    if (centavosDigitados(_controle.text) != widget.cents) {
      _controle.text = formatarCentavos(widget.cents);
    }
  }

  @override
  void dispose() {
    _controle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final acima = widget.cents > widget.maxCents;
    return Row(
      children: [
        const Expanded(child: Text('Desconto')),
        SizedBox(
          width: 140,
          child: TextField(
            key: const Key('order-discount'),
            controller: _controle,
            textAlign: TextAlign.right,
            keyboardType: TextInputType.number,
            inputFormatters: [_CentavosFormatter()],
            decoration: InputDecoration(
              isDense: true,
              prefixText: '- R\$ ',
              errorText: acima ? 'Maior que o subtotal' : null,
            ),
            onChanged: (texto) => widget.onChanged(centavosDigitados(texto)),
          ),
        ),
      ],
    );
  }
}
