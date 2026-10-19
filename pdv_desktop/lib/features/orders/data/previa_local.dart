import '../../home/data/fechamento_local.dart';
import 'order_draft_cart.dart';

export '../../home/data/fechamento_local.dart'
    show FechamentoLocal, FechamentoRecusado, aprovaOProprioDesconto, centavos;

/// O pagamento abre NA HORA, já com a conta certa.
///
/// O pedido está montado no PDV: esperar o servidor simular a venda inteira
/// (60 a 120 consultas) antes de mostrar a tela era 1 a 3 s com o cliente na
/// frente do caixa — mais com comanda. A conta sai daqui
/// (`fechamento_local.dart`) e o servidor a confere na conclusão: o total
/// mostrado vai junto e ele recusa (409) se não bater.
///
/// Com comanda, abre na hora quando a conta de TODOS os cartões já chegou (é
/// ela que diz o que cobrar). Cartão cuja conta ainda está vindo, ou sem nada
/// a cobrar, espera o servidor: é ele quem diz "já foi paga", "está em outra
/// conta" ou "nada a cobrar", e abre o pedido certo.
bool podeAbrirNaHora(OrderDraftCart draft) {
  if (draft.isEmpty) return false;
  for (final comanda in draft.commands) {
    final itens = draft.commandItems['${comanda['id']}'];
    if (itens == null || itens.isEmpty) return false;
  }
  return true;
}

/// O pedido que a tela de pagamento mostra: itens, taxa e total.
///
/// Promoção já vem no preço de cada item (`current_price` do catálogo); a taxa
/// é a padrão do restaurante. O cupom não entra aqui — ele vai ao servidor
/// quando é digitado.
Map<String, dynamic> previaLocal(
  OrderDraftCart draft, {
  required String percentualDaTaxa,
}) {
  final subtotal = reais(centavos(draft.total));
  return FechamentoLocal.aplicar(
    {
      'id': draft.orderId,
      'order_type': draft.orderType,
      'payment_status': 'pending',
      'subtotal': subtotal,
      // O padrão do pedido no servidor (`Order.service_fee_enabled`).
      'service_fee_enabled': true,
      'discount': '0.00',
      'coupon_discount': '0.00',
      'coupon_code': '',
      'delivery_fee': '0.00',
      'fiscal_customer_cpf': '',
      'fiscal_customer_cnpj': '',
      'total': subtotal,
      'items': draft.cartItems,
    },
    const {'service_fee_enabled': true},
    percentualDaTaxa: percentualDaTaxa,
  );
}

/// As anotações das comandas que o caixa VIU ao abrir o pagamento.
///
/// A conclusão leva só estas (`command_items`): o que o garçom lançar depois
/// fica para a próxima conta, em vez de entrar num total maior que o recebido.
List<String> anotacoesVistas(OrderDraftCart draft) => [
  for (final item in draft.itensJaLancados)
    if ('${item['id'] ?? ''}'.isNotEmpty) '${item['id']}',
];
