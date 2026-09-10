/// Aritmética decimal para valores que precisam coincidir com o backend.
///
/// `double` não representa centavos exatamente. Esta classe converte a forma
/// textual do valor em uma fração inteira e só arredonda no ponto em que o
/// backend também usa `Decimal(...).quantize(0.01, ROUND_HALF_UP)`.
abstract final class DecimalMoney {
  static int minorUnits(Object? value) {
    final ratio = _ratio(value);
    return _roundHalfUp(ratio.$1 * BigInt.from(100), ratio.$2);
  }

  static int multiplyToMinorUnits(Object? value, Object? multiplier) {
    final amount = _ratio(value);
    final factor = _ratio(multiplier);
    return _roundHalfUp(
      amount.$1 * factor.$1 * BigInt.from(100),
      amount.$2 * factor.$2,
    );
  }

  static int percentageToMinorUnits(Object? value, Object? percentage) {
    final amountInCents = minorUnits(value);
    final rate = _ratio(percentage);
    return _roundHalfUp(
      BigInt.from(amountInCents) * rate.$1,
      rate.$2 * BigInt.from(100),
    );
  }

  static double asNumber(int value) => value / 100;

  static String format(int value) {
    final sign = value < 0 ? '-' : '';
    final digits = value.abs().toString().padLeft(3, '0');
    return '$sign${digits.substring(0, digits.length - 2)}.'
        '${digits.substring(digits.length - 2)}';
  }

  static (BigInt, BigInt) _ratio(Object? value) {
    final text = '${value ?? 0}'.trim().replaceAll(',', '.');
    final match = RegExp(
      r'^([+-]?)(\d*)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$',
    ).firstMatch(text);
    if (match == null) return (BigInt.zero, BigInt.one);

    final whole = match.group(2)!.isEmpty ? '0' : match.group(2)!;
    final fraction = match.group(3) ?? '';
    var numerator = BigInt.parse('$whole$fraction');
    if (match.group(1) == '-') numerator = -numerator;
    final exponent = int.tryParse(match.group(4) ?? '') ?? 0;
    final scale = fraction.length - exponent;
    if (scale <= 0) {
      return (numerator * _powerOfTen(-scale), BigInt.one);
    }
    return (numerator, _powerOfTen(scale));
  }

  static BigInt _powerOfTen(int exponent) => BigInt.from(10).pow(exponent);

  static int _roundHalfUp(BigInt numerator, BigInt denominator) {
    final negative = numerator.isNegative;
    final absolute = numerator.abs();
    var result = absolute ~/ denominator;
    if ((absolute.remainder(denominator) * BigInt.two) >= denominator) {
      result += BigInt.one;
    }
    return (negative ? -result : result).toInt();
  }
}
