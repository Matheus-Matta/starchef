/// Conversões tolerantes para valores vindos da API.
abstract final class ValueFormatters {
  static double number(Object? value) => double.tryParse('${value ?? 0}') ?? 0;

  static String money(Object? value) =>
      'R\$ ${number(value).toStringAsFixed(2).replaceAll('.', ',')}';
}
