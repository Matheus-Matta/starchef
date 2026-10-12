import 'order_draft_cart.dart';

/// O pedido aberto na tela pode ser RELIDO do servidor?
///
/// A prévia da tela de pagamento (`simulada`) não existe lá até a conclusão.
/// Relida a cada evento do tempo real — de QUALQUER caixa ou garçom da loja —,
/// cada movimento do salão virava um 404 na cara do caixa: "Não foi possível
/// aplicar a atualização em tempo real".
extension PedidoNaTela on OrderDraftCart {
  bool pedidoExisteNoServidor(Map<String, dynamic>? pedido) =>
      pedido != null && !simulada;
}
