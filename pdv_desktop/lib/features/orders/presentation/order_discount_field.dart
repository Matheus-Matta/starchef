import 'package:flutter/services.dart';

import '../../../core/formatters/decimal_money.dart';

/// Os centavos do desconto, digitado na tela de pagamento.
///
/// Cada dígito entra pelos centavos, como no teclado de pagamento: "5", "50",
/// "500" vira R$ 0,05, R$ 0,50, R$ 5,00. O campo saiu do carrinho e foi para
/// a tela de pagamento (`payment_adjustments.dart`), junto da taxa e do CPF.

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

/// Mantém o campo nos centavos a cada tecla, sem vírgula digitada à mão.
class CentavosFormatter extends TextInputFormatter {
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
