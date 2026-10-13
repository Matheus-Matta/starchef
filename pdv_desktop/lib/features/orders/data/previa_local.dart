import 'order_draft_cart.dart';

/// O pagamento abre NA HORA para a venda de balcão.
///
/// O pedido já está montado no PDV: esperar o servidor calcular o total antes
/// de mostrar a tela era 1 a 3 s com o cliente na frente do caixa. A tela abre
/// com a prévia local e o servidor confirma em segundo plano; a validação de
/// verdade é a da conclusão (o total mostrado vai junto e o servidor recusa
/// se não bater).
///
/// Com comanda, não: o que ela já tem lançado e as recusas dela (já paga, em
/// outro pedido) são do servidor, e abrir antes dele responderia com o
/// pedido errado na tela.
bool podeAbrirNaHora(OrderDraftCart draft) =>
    draft.commands.isEmpty && draft.lines.isNotEmpty;

/// O pedido que a tela de pagamento mostra ENQUANTO o servidor confirma.
///
/// Só o que o PDV sabe sem perguntar: os itens e a soma deles. Taxa de
/// serviço, promoção e cupom chegam com a confirmação, e a tela se corrige
/// sozinha. Antes dela o Finalizar espera — nunca conclui sobre esta prévia.
Map<String, dynamic> previaLocal(OrderDraftCart draft) {
  final total = draft.total;
  final itens = draft.cartItems;
  return {
    'id': draft.orderId,
    'order_type': draft.orderType,
    'payment_status': 'pending',
    'subtotal': total,
    'service_fee': 0,
    // O padrão do pedido no servidor (`Order.service_fee_enabled`).
    'service_fee_enabled': true,
    'discount': 0,
    'coupon_discount': 0,
    'coupon_code': '',
    'delivery_fee': 0,
    'fiscal_customer_cpf': '',
    'fiscal_customer_cnpj': '',
    'total': total,
    'items': itens,
    previaLocalMarca: true,
  };
}

/// Marca da prévia que ainda não foi confirmada pelo servidor.
const previaLocalMarca = '_previa_local';
