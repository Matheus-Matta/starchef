import '../../../core/formatters/decimal_money.dart';

enum WeighedProductEntryMode { weight, amount }

/// Conversões exatas para o campo de peso/preço do produto vendido por kg.
abstract final class WeighedProductMath {
  /// Aceita `0,500`, `20,00`, `1.234,56` e também o prefixo `R$`.
  static int amountInCents(String input) {
    final value = _normalize(input);
    if (value.isEmpty) return 0;
    return DecimalMoney.minorUnits(value);
  }

  /// Converte o texto de peso em milésimos de kg (gramas).
  static int weightGramsFromInput(String input) {
    final value = _normalize(input);
    final parsed = double.tryParse(value);
    if (parsed == null || !parsed.isFinite || parsed <= 0) return 0;
    return (parsed * 1000).round();
  }

  /// O pedido guarda o peso com três casas; por isso a conversão é ao grama.
  static int weightGramsForAmount({
    required String amount,
    required Object? pricePerKg,
  }) {
    final amountCents = amountInCents(amount);
    final priceCents = DecimalMoney.minorUnits(pricePerKg);
    if (amountCents <= 0 || priceCents <= 0) return 0;
    return _roundHalfUp(
      BigInt.from(amountCents) * BigInt.from(1000),
      BigInt.from(priceCents),
    );
  }

  static int totalInCents(int weightGrams, Object? pricePerKg) {
    if (weightGrams <= 0) return 0;
    return DecimalMoney.multiplyToMinorUnits(
      pricePerKg,
      (weightGrams / 1000).toStringAsFixed(3),
    );
  }

  static String weightText(int weightGrams) =>
      (weightGrams / 1000).toStringAsFixed(3);

  static String _normalize(String input) {
    var value = input.trim().replaceAll(RegExp(r'[^0-9,.-]'), '');
    if (value.contains(',')) {
      value = value.replaceAll('.', '').replaceAll(',', '.');
    }
    return value;
  }

  static int _roundHalfUp(BigInt numerator, BigInt denominator) {
    var result = numerator ~/ denominator;
    if ((numerator.remainder(denominator) * BigInt.two) >= denominator) {
      result += BigInt.one;
    }
    return result.toInt();
  }
}
