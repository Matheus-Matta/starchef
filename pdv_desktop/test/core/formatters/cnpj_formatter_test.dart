import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/formatters/cnpj_formatter.dart';

/// CNPJ na NFC-e: o numérico de sempre e o alfanumérico novo da Receita.
///
/// O campo aceita letras (o alfanumérico tem letras nas 12 primeiras
/// posições), então o operador PODE digitar letra no dígito verificador. A
/// conferência fazia `int.parse` ali e estourava `FormatException` em vez de
/// dizer "CNPJ inválido".
void main() {
  test('aceita o numérico e o alfanumérico, com ou sem máscara', () {
    expect(isValidCnpj('11.222.333/0001-81'), isTrue);
    expect(isValidCnpj('11222333000181'), isTrue);
    expect(isValidCnpj('12.ABC.345/01DE-35'), isTrue);
    expect(isValidCnpj('12abc34501de35'), isTrue);
  });

  test('letra no dígito verificador é CNPJ inválido, não exceção', () {
    expect(isValidCnpj('11.222.333/0001-8A'), isFalse);
    expect(isValidCnpj('12ABC34501DEXX'), isFalse);
  });

  test('recusa dígito errado, tamanho errado, repetido e vazio', () {
    expect(isValidCnpj('11222333000182'), isFalse);
    expect(isValidCnpj('1122233300018'), isFalse);
    expect(isValidCnpj('00000000000000'), isFalse);
    expect(isValidCnpj(''), isFalse);
    expect(isValidCnpj(null), isFalse);
  });

  test('máscara não passa de 14 caracteres úteis e mantém letras', () {
    expect(formatCnpj('12abc34501de35999'), '12.ABC.345/01DE-35');
    expect(cnpjDigits('12.ABC.345/01DE-35'), '12ABC34501DE35');
  });
}
