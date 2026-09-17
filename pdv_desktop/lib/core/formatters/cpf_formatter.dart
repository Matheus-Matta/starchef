import 'package:flutter/services.dart';

String cpfDigits(Object? value) {
  final digits = '${value ?? ''}'.replaceAll(RegExp(r'\D'), '');
  return digits.length <= 11 ? digits : digits.substring(0, 11);
}

String formatCpf(Object? value) {
  final digits = cpfDigits(value);
  final buffer = StringBuffer();
  for (var index = 0; index < digits.length; index += 1) {
    if (index == 3 || index == 6) buffer.write('.');
    if (index == 9) buffer.write('-');
    buffer.write(digits[index]);
  }
  return buffer.toString();
}

bool isValidCpf(Object? value) {
  final cpf = cpfDigits(value);
  if (cpf.length != 11 || cpf.split('').every((digit) => digit == cpf[0])) {
    return false;
  }
  for (final length in [9, 10]) {
    var total = 0;
    for (var index = 0; index < length; index += 1) {
      total += int.parse(cpf[index]) * (length + 1 - index);
    }
    final remainder = (total * 10) % 11;
    final expected = remainder == 10 ? 0 : remainder;
    if (int.parse(cpf[length]) != expected) return false;
  }
  return true;
}

class CpfInputFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    final formatted = formatCpf(newValue.text);
    return TextEditingValue(
      text: formatted,
      selection: TextSelection.collapsed(offset: formatted.length),
    );
  }
}
