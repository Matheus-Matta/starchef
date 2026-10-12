import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/formatters/documento_fiscal.dart';

/// Um campo só para CPF ou CNPJ: o tamanho decide o tipo.
void main() {
  test('o tamanho decide a mascara', () {
    expect(documentoFormatado('52998224725'), '529.982.247-25');
    expect(documentoFormatado('11222333000181'), '11.222.333/0001-81');
    expect(documentoFormatado('123'), '123');
  });

  test('vazio, CPF e CNPJ validos passam; o resto nao', () {
    expect(documentoValido(''), isTrue);
    expect(documentoValido('52998224725'), isTrue);
    expect(documentoValido('11222333000181'), isTrue);
    expect(documentoValido('11111111111'), isFalse);
    expect(documentoValido('5299822472'), isFalse);
  });

  test('so os digitos do que foi digitado', () {
    expect(documentoDigitos('529.982.247-25'), '52998224725');
  });
}
