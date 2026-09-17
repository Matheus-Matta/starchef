/// Conversões tolerantes para valores vindos da API.
///
/// A API devolve números ora como `num`, ora como string (`"12.50"`), e o
/// operador digita com vírgula. Concentrar a conversão aqui evita que cada
/// tela reinvente a própria regra e discorde das outras.
abstract final class ValueFormatters {
  /// Converte qualquer representação numérica em `double`, com zero como
  /// último recurso. Aceita vírgula decimal.
  static double number(Object? value) {
    if (value is num) return value.toDouble();
    if (value == null) return 0;
    return double.tryParse('$value'.trim().replaceAll(',', '.')) ?? 0;
  }

  /// Como [number], mas devolve `null` quando não há valor utilizável — para
  /// distinguir "campo ausente" de "zero".
  static double? optionalNumber(Object? value) {
    if (value is num) return value.toDouble();
    final text = '${value ?? ''}'.trim().replaceAll(',', '.');
    return text.isEmpty ? null : double.tryParse(text);
  }

  static int integer(Object? value, {int fallback = 0}) {
    if (value is num) return value.toInt();
    return int.tryParse('${value ?? ''}'.trim()) ?? fallback;
  }

  static String money(Object? value) =>
      'R\$ ${number(value).toStringAsFixed(2).replaceAll('.', ',')}';

  /// Peso com as três casas usadas pelas balanças.
  static String weight(Object? value) =>
      '${number(value).toStringAsFixed(3).replaceAll('.', ',')} kg';

  /// Normaliza um identificador vindo da API.
  ///
  /// Um relacionamento nulo pode chegar como `null`, string vazia ou a string
  /// literal `"null"`; todos significam "sem vínculo".
  static String? nullableId(Object? value) {
    final normalized = '${value ?? ''}'.trim();
    return normalized.isEmpty || normalized == 'null' ? null : normalized;
  }
}
