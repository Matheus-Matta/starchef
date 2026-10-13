import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/previa_local.dart';

/// O pagamento abre com o pedido que o PDV já montou.
///
/// Esperar o servidor calcular antes de mostrar a tela custava 1 a 3 s na
/// nuvem. A prévia é só exibição: a conclusão espera a confirmação.
OrderDraftLine _linha(String nome, double preco, double qtd) => OrderDraftLine(
  id: nome,
  productId: 'p-$nome',
  productName: nome,
  quantity: qtd,
  unitPrice: preco,
);

void main() {
  test('previa leva os itens, a soma e o id da venda', () {
    final draft = OrderDraftCart()
      ..add(_linha('Cafe', 5, 2))
      ..add(_linha('Pao', 3.5, 1));

    final previa = previaLocal(draft);

    expect(previa['id'], draft.orderId);
    expect(previa['total'], 13.5);
    expect((previa['items'] as List).length, 2);
    expect(previa[previaLocalMarca], isTrue);
    expect(previa['payment_status'], 'pending');
  });

  test('balcao abre na hora; com comanda espera o servidor', () {
    final balcao = OrderDraftCart()..add(_linha('Cafe', 5, 1));
    expect(podeAbrirNaHora(balcao), isTrue);

    final comComanda = OrderDraftCart()..add(_linha('Cafe', 5, 1));
    comComanda.commands.add({'id': 'c1', 'number': 3});
    expect(podeAbrirNaHora(comComanda), isFalse);
  });

  test('rascunho sem linha nova nao abre na hora', () {
    expect(podeAbrirNaHora(OrderDraftCart()), isFalse);
  });
}
