import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/pedido_na_tela.dart';

/// A prévia da tela de pagamento NÃO existe no servidor: não é relida.
///
/// Na tela de pagamento o pedido mostrado é a simulação (`simular`), que só
/// vira pedido na conclusão. Todo evento de pedido do tempo real — de
/// QUALQUER caixa ou garçom da loja — relia o pedido da tela pelo id da
/// prévia, recebia 404 e mostrava "Não foi possível aplicar a atualização em
/// tempo real" a cada movimento do salão.
void main() {
  test('pedido gravado e relido', () {
    final draft = OrderDraftCart();
    expect(draft.pedidoExisteNoServidor({'id': 'p1'}), isTrue);
  });

  test('previa simulada nao e relida', () {
    final draft = OrderDraftCart()..simulada = true;
    expect(draft.pedidoExisteNoServidor({'id': 'previa'}), isFalse);
  });

  test('sem pedido na tela, nada a reler', () {
    expect(OrderDraftCart().pedidoExisteNoServidor(null), isFalse);
  });
}
