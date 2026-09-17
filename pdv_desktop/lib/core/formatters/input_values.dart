/// Validação de número vindo do corpo de uma operação, antes de gravar.
///
/// [ValueFormatters.number] existe para EXIBIR: ele devolve `0` para qualquer
/// coisa que não parseia, o que é certo numa tela (melhor mostrar "0,00" do que
/// quebrar) e errado numa gravação. Usado no caminho de escrita, ele fazia:
///
/// - `quantity: "duas"` virar `0` e depois `1`, cobrado do cliente;
/// - `amount` ausente virar `0,00`, registrando um recebimento de nada;
/// - `opening_amount: "cem reais"` abrir a gaveta com zero, e o fechamento do
///   dia acusar diferença que ninguém causou.
///
/// Pior: o backend RECUSA esses mesmos valores. A operação subia na fila e
/// voltava `FAILED` depois de a venda já ter sido impressa e cobrada. Aqui as
/// duas pontas passam a dizer a mesma coisa, e o operador descobre na hora.
library;

import '../network/api_exception.dart';

/// Teto de um campo de dinheiro no backend (`max_digits: 12, decimal_places: 2`).
const double maxMoneyValue = 9999999999.99;

/// Teto de quantidade de item (`max_digits: 10, decimal_places: 3`).
const double maxQuantityValue = 9999999.999;

/// Converte para número ou recusa com 400 e a razão no campo certo.
///
/// [padrao] é usado quando o valor vem ausente; sem ele, ausente é erro —
/// "não informou" e "informou zero" são coisas diferentes quando é dinheiro.
double requireNumber(
  Object? value, {
  required String field,
  String? label,
  double? padrao,
  double? minimo,
  double maximo = maxMoneyValue,
}) {
  final nome = label ?? field;
  if (value == null || (value is String && value.trim().isEmpty)) {
    if (padrao != null) return padrao;
    throw ApiException('Informe $nome.', statusCode: 400);
  }
  if (value is bool) {
    throw ApiException('Informe um número em $nome.', statusCode: 400);
  }
  final double? parsed = value is num
      ? value.toDouble()
      : double.tryParse('$value'.trim().replaceAll(',', '.'));
  if (parsed == null || parsed.isNaN || parsed.isInfinite) {
    throw ApiException('Informe um número válido em $nome.', statusCode: 400);
  }
  if (minimo != null && parsed < minimo) {
    throw ApiException('$nome não pode ser negativo.', statusCode: 400);
  }
  if (parsed.abs() > maximo) {
    throw ApiException('O valor informado em $nome é grande demais.', statusCode: 400);
  }
  return parsed;
}

/// Dinheiro: nunca negativo por padrão, sempre dentro do que a coluna aceita.
double requireMoney(
  Object? value, {
  required String field,
  String? label,
  double? padrao,
  bool permiteNegativo = false,
}) => requireNumber(
  value,
  field: field,
  label: label,
  padrao: padrao,
  minimo: permiteNegativo ? null : 0,
);

/// Quantidade: estritamente maior que zero.
double requireQuantity(
  Object? value, {
  String field = 'quantity',
  String label = 'a quantidade',
  double? padrao,
}) {
  final parsed = requireNumber(
    value,
    field: field,
    label: label,
    padrao: padrao,
    maximo: maxQuantityValue,
  );
  if (parsed <= 0) {
    throw ApiException('$label precisa ser maior que zero.', statusCode: 400);
  }
  return parsed;
}
