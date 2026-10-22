import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pilha_de_desfazer.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';

/// O Esc desfaz do mais recente para o mais antigo, e só na tela dele.
void main() {
  test('desfaz do mais recente para o mais antigo', () {
    final pilha = PilhaDeDesfazer();
    final feitos = <String>[];
    pilha.empilhar('payment', 'Dinheiro', () => feitos.add('dinheiro'));
    pilha.empilhar('payment', 'Crédito', () => feitos.add('credito'));

    expect(pilha.desfazerUltimo('payment'), 'Crédito');
    expect(pilha.desfazerUltimo('payment'), 'Dinheiro');
    expect(pilha.desfazerUltimo('payment'), isNull);
    expect(feitos, ['credito', 'dinheiro']);
  });

  test('o Esc de uma tela não desfaz o que é da outra', () {
    final pilha = PilhaDeDesfazer();
    final feitos = <String>[];
    pilha.empilhar('order', 'Prato', () => feitos.add('prato'));
    pilha.empilhar('payment', 'Crédito', () => feitos.add('credito'));

    expect(pilha.desfazerUltimo('order'), 'Prato');
    pilha.esquecer('payment');

    expect(pilha.temEm('payment'), isFalse);
    expect(feitos, ['prato']);
  });

  OrderDraftLine linha(String produto, {double? peso}) => OrderDraftLine(
    id: '',
    productId: produto,
    productName: produto,
    quantity: peso ?? 1,
    unitPrice: 10,
    weightKg: peso,
    pricingUnit: peso == null ? null : 'kg',
  );

  test('desfazer a inclusão tira só o que ela somou', () {
    final carrinho = OrderDraftCart();
    carrinho.add(linha('cafe'));
    final segunda = carrinho.add(linha('cafe'));

    carrinho.desfazerInclusao(segunda);

    expect(carrinho.lines.single.quantity, 1);
  });

  test('desfazer a pesagem tira aquele prato, não o outro', () {
    final carrinho = OrderDraftCart();
    carrinho.add(linha('buffet', peso: 0.5));
    final segundo = carrinho.add(linha('buffet', peso: 0.7));

    carrinho.desfazerInclusao(segundo);

    expect(carrinho.lines.map((l) => l.weightKg), [0.5]);
  });
}
