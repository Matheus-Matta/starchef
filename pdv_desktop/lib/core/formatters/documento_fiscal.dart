import 'cnpj_formatter.dart';
import 'cpf_formatter.dart';

/// CPF ou CNPJ num campo só: quem decide qual é, é o TAMANHO (11 ou 14).
///
/// O caixa não escolhe o tipo antes de digitar — o cliente dita os números, e
/// pedir "pessoa física ou jurídica?" antes era um passo a mais na fila.

/// Só os dígitos do que foi digitado ("529.982.247-25" → "52998224725").
String documentoDigitos(String texto) => texto.replaceAll(RegExp(r'\D'), '');

/// Com a máscara do tipo: 11 dígitos = CPF, 14 = CNPJ; o resto, como veio.
String documentoFormatado(String digitos) => switch (digitos.length) {
  14 => formatCnpj(digitos),
  11 => formatCpf(digitos),
  _ => digitos,
};

/// Vazio (tira da nota), CPF válido ou CNPJ válido.
bool documentoValido(String digitos) =>
    digitos.isEmpty ||
    (digitos.length == 11 && isValidCpf(digitos)) ||
    (digitos.length == 14 && isValidCnpj(digitos));
