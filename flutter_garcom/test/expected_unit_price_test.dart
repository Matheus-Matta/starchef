import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/features/orders/presentation/order_formatters.dart';

/// Preço de uma unidade com variação e adicionais — mesma fórmula do PDV
/// desktop (`OrderPresenter.expectedUnitPrice`). Existe porque o app não
/// tinha NENHUMA tela para escolher variação/adicional; sem este cálculo, o
/// "Total do item" mostrado ao garçom não batia com o que o backend cobra.
void main() {
  final produto = {
    'sale_price': '20.00',
    'variations': [
      {'id': 'v-media', 'name': 'Média', 'price_delta': '0.00'},
      {'id': 'v-grande', 'name': 'Grande', 'price_delta': '8.50'},
      {
        'id': 'v-desativada',
        'name': 'Descontinuada',
        'price_delta': '2.00',
        'is_active': false,
      },
    ],
    'addons': [
      {'id': 'a-bacon', 'name': 'Bacon', 'price': '4.00'},
      {'id': 'a-queijo', 'name': 'Queijo extra', 'price': '3.50'},
    ],
  };

  test('sem variação nem adicional, é só o preço base', () {
    expect(expectedUnitPrice(produto), 20.00);
  });

  test('variação soma o price_delta', () {
    expect(expectedUnitPrice(produto, variationId: 'v-grande'), 28.50);
  });

  test('variação de delta zero não muda o preço', () {
    expect(expectedUnitPrice(produto, variationId: 'v-media'), 20.00);
  });

  test('cada adicional marcado soma o próprio preço', () {
    expect(
      expectedUnitPrice(produto, addonIds: ['a-bacon']),
      24.00,
    );
    expect(
      expectedUnitPrice(produto, addonIds: ['a-bacon', 'a-queijo']),
      27.50,
    );
  });

  test('variação e adicionais somam juntos', () {
    expect(
      expectedUnitPrice(
        produto,
        variationId: 'v-grande',
        addonIds: ['a-bacon', 'a-queijo'],
      ),
      36.00,
    );
  });

  test('variationId que não existe no produto não soma nada', () {
    expect(expectedUnitPrice(produto, variationId: 'nao-existe'), 20.00);
  });

  test('produto sem variations/addons no payload não quebra', () {
    expect(expectedUnitPrice({'sale_price': '15.00'}), 15.00);
  });
}
