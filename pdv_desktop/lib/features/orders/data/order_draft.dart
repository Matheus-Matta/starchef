/// O carrinho que ainda NÃO existe no servidor.
///
/// O posto de venda abre direto no catálogo, e passar produtos não cria nada:
/// as linhas ficam aqui, na memória da tela, até alguém de fora precisar do
/// pedido — a cozinha, para imprimir um ticket, ou o caixa, para anexar um
/// recebimento. É o mesmo desenho da web (`composables/useOrderDraft.js`), e é
/// de propósito: quem alterna entre os dois no turno encontra o mesmo gesto.
///
/// O que isso evita: antes, escolher a comanda 13 e desistir deixava o cartão
/// ocupado com um pedido vazio que alguém tinha de cancelar depois. Um
/// rascunho abandonado aqui simplesmente deixa de existir quando a tela sai.
///
/// **O dinheiro daqui é só para MOSTRAR.** Quem soma de verdade é o servidor,
/// que conhece taxa de serviço, desconto e o preço em vigor no momento do
/// lançamento. O total desta classe serve para o operador conferir o carrinho
/// antes de abrir o pedido — nunca para cobrar.
library;

import 'package:flutter/foundation.dart';

/// Uma linha do rascunho.
///
/// Guarda o que é preciso para RECRIAR o lançamento no servidor, não o que o
/// servidor devolveria: o preço unitário vai como `expected_unit_price`, que é
/// conferência, e a resposta autoritativa chega na materialização.
@immutable
class OrderDraftLine {
  const OrderDraftLine({
    required this.id,
    required this.productId,
    required this.productName,
    required this.quantity,
    required this.unitPrice,
    this.variationId,
    this.addonIds = const [],
    this.customerNote = '',
    this.weightKg,
    this.scaleReadingId,
    this.pricingUnit,
  });

  final String id;
  final String productId;
  final String productName;
  final double quantity;
  final double unitPrice;
  final String? variationId;
  final List<String> addonIds;
  final String customerNote;

  /// Produto pesado: a quantidade é o peso, e ele nunca agrupa com outro.
  final double? weightKg;
  final String? scaleReadingId;
  final String? pricingUnit;

  bool get isWeighed => weightKg != null || scaleReadingId != null;

  double get total => quantity * unitPrice;

  /// Duas linhas são "o mesmo lançamento" quando tudo o que o cliente pediu
  /// coincide. Peso fica de fora: dois cortes de 300 g não são 600 g de um
  /// corte só — cada pesagem tem a sua leitura de balança.
  bool matches(OrderDraftLine other) =>
      !isWeighed &&
      !other.isWeighed &&
      productId == other.productId &&
      variationId == other.variationId &&
      customerNote == other.customerNote &&
      listEquals(addonIds, other.addonIds);

  OrderDraftLine copyWith({double? quantity}) => OrderDraftLine(
    id: id,
    productId: productId,
    productName: productName,
    quantity: quantity ?? this.quantity,
    unitPrice: unitPrice,
    variationId: variationId,
    addonIds: addonIds,
    customerNote: customerNote,
    weightKg: weightKg,
    scaleReadingId: scaleReadingId,
    pricingUnit: pricingUnit,
  );

  /// O formato que o painel do carrinho já sabe desenhar.
  ///
  /// O carrinho é o MESMO widget do pedido de verdade — ele não deve saber se
  /// está mostrando rascunho ou pedido aberto. Duas listas com aparências
  /// diferentes para a mesma coisa seriam duas telas a manter, e o operador
  /// leria "carrinho" de dois jeitos no mesmo turno.
  Map<String, dynamic> toCartItem() => {
    'id': id,
    'product_name': productName,
    'quantity': quantity,
    'unit_price': unitPrice,
    'total_price': total,
    // `pending` é o que o carrinho entende por "ainda não foi para a cozinha",
    // que é exatamente a situação de toda linha de rascunho.
    'status': 'pending',
    'variations': const [],
    'addons': const [],
    'customer_note': customerNote,
    if (pricingUnit != null) 'pricing_unit': pricingUnit,
  };

  /// O corpo de `POST /orders/<id>/items/`.
  Map<String, dynamic> toItemPayload() => {
    'product': productId,
    if (isWeighed) ...{
      if (scaleReadingId != null)
        'scale_reading': scaleReadingId
      else
        'weight_kg': weightKg!.toStringAsFixed(3),
    } else
      'quantity': quantity.round(),
    'variations': variationId == null ? const [] : [variationId],
    'addons': addonIds,
    if (!isWeighed) 'expected_unit_price': unitPrice.toStringAsFixed(2),
    'customer_note': customerNote,
  };
}
