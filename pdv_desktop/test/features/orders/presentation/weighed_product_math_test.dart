import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/weighed_product_math.dart';

void main() {
  test('converte reais em gramas com arredondamento de um grama', () {
    expect(
      WeighedProductMath.weightGramsForAmount(
        amount: 'R\$ 20,00',
        pricePerKg: '40.00',
      ),
      500,
    );
  });

  test('total mostra o valor real do peso arredondado', () {
    final grams = WeighedProductMath.weightGramsForAmount(
      amount: '10,00',
      pricePerKg: '49.90',
    );

    expect(grams, 200);
    expect(WeighedProductMath.totalInCents(grams, '49.90'), 998);
  });

  test('interpreta peso em gramas e valor digitado no padrão brasileiro', () {
    expect(WeighedProductMath.weightGramsFromInput('0,500'), 500);
    expect(WeighedProductMath.amountInCents('1.234,56'), 123456);
  });
}
