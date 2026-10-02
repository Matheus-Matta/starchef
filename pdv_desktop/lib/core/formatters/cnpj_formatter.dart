import 'package:flutter/services.dart';

String cnpjDigits(Object? value) {
  final characters = '${value ?? ''}'.toUpperCase().replaceAll(
    RegExp(r'[^A-Z0-9]'),
    '',
  );
  return characters.length <= 14 ? characters : characters.substring(0, 14);
}

String formatCnpj(Object? value) {
  final digits = cnpjDigits(value);
  final buffer = StringBuffer();
  for (var index = 0; index < digits.length; index += 1) {
    if (index == 2) buffer.write('.');
    if (index == 5) buffer.write('.');
    if (index == 8) buffer.write('/');
    if (index == 12) buffer.write('-');
    buffer.write(digits[index]);
  }
  return buffer.toString();
}

bool isValidCnpj(Object? value) {
  final cnpj = cnpjDigits(value);
  if (cnpj.length != 14 || cnpj.split('').every((digit) => digit == cnpj[0])) {
    return false;
  }
  // Os dois verificadores são sempre números, mesmo no CNPJ alfanumérico. O
  // campo aceita letras, e sem esta conferência o `int.parse` lá embaixo
  // estourava em vez de dizer "inválido".
  if (!RegExp(r'^\d{2}$').hasMatch(cnpj.substring(12))) return false;
  const firstWeights = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  for (final length in [12, 13]) {
    final weights = length == 12 ? firstWeights : [6, ...firstWeights];
    var total = 0;
    for (var index = 0; index < length; index += 1) {
      total += (cnpj.codeUnitAt(index) - 48) * weights[index];
    }
    final remainder = total % 11;
    final expected = remainder < 2 ? 0 : 11 - remainder;
    if (int.parse(cnpj[length]) != expected) return false;
  }
  return true;
}

class CnpjInputFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final formatted = formatCnpj(newValue.text);
    return TextEditingValue(
      text: formatted,
      selection: TextSelection.collapsed(offset: formatted.length),
    );
  }
}
