import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_commands.dart';
import 'package:starchef_pdv_desktop/features/orders/data/previa_local.dart';

/// O pagamento abre com o pedido que o PDV já montou — e com a conta CERTA.
///
/// Esperar o servidor simular a venda inteira custava 1 a 3 s na loja e na
/// nuvem, e mais ainda com comanda. A prévia agora já traz a taxa e o total
/// (`fechamento_local.dart`); o servidor confere tudo na conclusão.
OrderDraftLine _linha(String nome, double preco, double qtd) => OrderDraftLine(
  id: nome,
  productId: 'p-$nome',
  productName: nome,
  quantity: qtd,
  unitPrice: preco,
);

Map<String, dynamic> _anotacao(String id, String valor) => {
  'id': id,
  'product_name': 'Chopp',
  'quantity': '1.000',
  'total_price': valor,
};

void main() {
  test('previa leva os itens, a taxa do restaurante e o total certo', () {
    final draft = OrderDraftCart()
      ..add(_linha('Cafe', 5, 2))
      ..add(_linha('Pao', 3.5, 1));

    final previa = previaLocal(draft, percentualDaTaxa: '10.00');

    expect(previa['id'], draft.orderId);
    expect(previa['subtotal'], '13.50');
    expect(previa['service_fee'], '1.35');
    expect(previa['total'], '14.85');
    expect((previa['items'] as List).length, 2);
    expect(previa['payment_status'], 'pending');
  });

  test('balcao abre na hora', () {
    expect(
      podeAbrirNaHora(OrderDraftCart()..add(_linha('Cafe', 5, 1))),
      isTrue,
    );
  });

  test(
    'comanda com a conta ja carregada abre na hora e marca o que foi visto',
    () {
      // Só pagar a comanda: nenhuma linha nova, a conta do cartão já na tela.
      final draft = OrderDraftCart()
        ..attachCommand(
          {'id': 'c1', 'number': 3},
          items: [_anotacao('a1', '25.00'), _anotacao('a2', '12.50')],
        );

      expect(podeAbrirNaHora(draft), isTrue);
      final previa = previaLocal(draft, percentualDaTaxa: '10.00');
      expect(previa['subtotal'], '37.50');
      expect(previa['total'], '41.25');
      // A conclusão leva SÓ estas anotações: o que o garçom lançar depois de o
      // caixa abrir o pagamento fica para a próxima conta.
      expect(anotacoesVistas(draft), ['a1', 'a2']);
    },
  );

  test('comanda cuja conta ainda esta chegando espera o servidor', () {
    final draft = OrderDraftCart()..add(_linha('Cafe', 5, 1));
    draft.commands.add({'id': 'c1', 'number': 3}); // itens ainda não vieram

    expect(podeAbrirNaHora(draft), isFalse);
  });

  test(
    'comanda sem nada a cobrar espera o servidor, que da a recusa certa',
    () {
      final draft = OrderDraftCart()..attachCommand({'id': 'c1', 'number': 3});
      draft.setCommandItems('c1', const []);

      expect(podeAbrirNaHora(draft), isFalse);
    },
  );

  test('rascunho vazio nao abre na hora', () {
    expect(podeAbrirNaHora(OrderDraftCart()), isFalse);
  });
}
