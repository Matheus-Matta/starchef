part of 'order_draft_cart.dart';

/// Incluir uma linha e desfazer a inclusão (o Esc da venda,
/// `pilha_de_desfazer.dart`).
extension DesfazerNoCarrinho on OrderDraftCart {
  /// Devolve a linha incluída (com o id que ganhou), para o Esc desfazer.
  OrderDraftLine add(OrderDraftLine line) {
    final pronta = line.id.isEmpty
        ? OrderDraftLine(
            id: LocalId.uuid(),
            productId: line.productId,
            productName: line.productName,
            quantity: line.quantity,
            unitPrice: line.unitPrice,
            variationId: line.variationId,
            addonIds: line.addonIds,
            customerNote: line.customerNote,
            weightKg: line.weightKg,
            scaleReadingId: line.scaleReadingId,
            pricingUnit: line.pricingUnit,
          )
        : line;

    final indice = _lines.indexWhere((atual) => atual.matches(pronta));
    if (indice >= 0) {
      _lines[indice] = _lines[indice].copyWith(
        quantity: _lines[indice].quantity + pronta.quantity,
      );
      return pronta;
    }
    _lines.add(pronta);
    return pronta;
  }

  /// Desfaz um [add]: tira a quantidade que ele somou, ou a linha inteira
  /// quando ela nasceu dele. É o Esc da venda (`pilha_de_desfazer.dart`):
  /// tirar o último prato passado sem apagar os que vieram antes.
  void desfazerInclusao(OrderDraftLine incluida) {
    // Pelo id (a pesagem nunca se junta a outra); senão, a linha somada.
    var indice = _lines.indexWhere((atual) => atual.id == incluida.id);
    if (indice < 0) {
      indice = _lines.indexWhere((atual) => atual.matches(incluida));
    }
    if (indice < 0) return;
    final resto = _lines[indice].quantity - incluida.quantity;
    if (resto <= 0.0000001) {
      _lines.removeAt(indice);
    } else {
      _lines[indice] = _lines[indice].copyWith(quantity: resto);
    }
  }
}
