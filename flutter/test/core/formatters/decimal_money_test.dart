import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/formatters/decimal_money.dart';
import 'package:starchef_pdv/features/orders/presentation/order_presenter.dart';

void main() {
  test('arredonda meio centavo para cima como Decimal do backend', () {
    expect(DecimalMoney.percentageToMinorUnits('43.15', 10), 432);

    final closed = OrderPresenter.closeOfflineOrder(
      {'subtotal': '43.15', 'discount': '0.00', 'delivery_fee': '0.00'},
      serviceFeeEnabled: true,
      serviceFeePercent: 10,
    );

    expect(closed['service_fee'], '4.32');
    expect(closed['total'], '47.47');
  });

  test('arredonda o total de cada item antes de somar o pedido', () {
    expect(DecimalMoney.multiplyToMinorUnits('8.75', '1.234'), 1080);

    final order = OrderPresenter.withItems(
      const {'service_fee': '0.00', 'delivery_fee': '0.00'},
      [
        {'status': 'pending', 'total_price': '10.80'},
        {'status': 'pending', 'total_price': '2.35'},
      ],
    );

    expect(order['subtotal'], 13.15);
    expect(order['total'], 13.15);
  });
}
