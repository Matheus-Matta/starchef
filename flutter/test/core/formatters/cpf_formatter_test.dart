import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/formatters/cpf_formatter.dart';

void main() {
  test('normaliza e formata CPF', () {
    expect(cpfDigits('123.456.789-09'), '12345678909');
    expect(formatCpf('12345678909'), '123.456.789-09');
  });

  test('valida os digitos verificadores', () {
    expect(isValidCpf('123.456.789-09'), isTrue);
    expect(isValidCpf('111.111.111-11'), isFalse);
    expect(isValidCpf('123'), isFalse);
  });
}
