// Ver `home_page.dart` para o motivo deste ignore na biblioteca.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O CUPOM DENTRO DA TELA DE PAGAMENTO — aplicar, trocar e retirar.
///
/// Existe porque o cliente lembra do cupom quando o caixa fala o total. É o
/// caso normal, não a exceção: ele tira o celular do bolso na hora de pagar.
/// Sem isto, o caixa teria de desfazer o fechamento e refazê-lo por causa de um
/// código — na frente dele.
///
/// QUEM VALIDA É O SERVIDOR, sempre. O terminal não sabe se este CPF já usou o
/// cupom, se o mínimo foi alcançado ou se ele venceu há uma hora; e uma
/// validação otimista aqui mostraria o desconto na tela para o servidor recusar
/// depois, com o cliente já tendo ouvido o valor menor.
///
/// A rota é a MESMA para os três gestos (`apply-coupon`, com `code` vazio
/// retirando). Uma rota por gesto faria esta tela escolher qual chamar a partir
/// de um campo de texto — e escolher errado em silêncio.
mixin _PaymentCouponSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  TextEditingController get couponCode;
  String get couponError;
  set couponError(String value);
  bool get couponBusy;
  set couponBusy(bool value);

  /// Desenhada por `_PaymentView`. Declarada aqui porque as linhas do cupom
  /// são do MESMO resumo: um estilo próprio faria "Cupom NATAL10" desalinhar
  /// de "Desconto" logo acima.
  Widget _paymentSummaryRow(String label, String value, {bool strong});
  void _valorSugeridoDoNovoTotal();

  /// O código que o pedido carrega agora, vazio quando não há cupom.
  String get _appliedCoupon => '${activeOrder?['coupon_code'] ?? ''}'.trim();

  double get _couponDiscount => _number(activeOrder?['coupon_discount']);

  /// Aplica, troca ou retira. `codigo` vazio retira.
  ///
  /// Não passa por `_work`: aquela trava existe para impedir duas operações de
  /// VENDA ao mesmo tempo, e ela DESISTE em silêncio quando já há uma em curso
  /// (`if (busy) return null`). Mexer no cupom acontece no meio do recebimento,
  /// com a tela ocupada — e uma desistência silenciosa aqui apagaria o gesto do
  /// operador sem dizer nada.
  Future<void> _aplicarCupom(String codigo) async {
    if (couponBusy || activeOrder == null) return;
    setState(() {
      couponBusy = true;
      couponError = '';
    });
    try {
      // Venda simulada: o cupom entra no fechamento e o servidor recalcula,
      // ainda sem gravar. Recusado, o erro vem igual.
      final simulada = draft.simulada;
      final fechamento = {...?draft.fechamento, 'coupon_code': codigo};
      final atualizado = simulada
          ? await OrderDraftMaterializer(
              api,
              accessToken: token,
            ).simular(draft, restaurantId: restaurantId, fechamento: fechamento)
          : await api.post(
              '/orders/${activeOrder!['id']}/apply-coupon/',
              body: {'code': codigo},
              accessToken: token,
            );
      if (simulada) draft.fechamento = fechamento;
      if (!mounted) return;
      // O pedido volta com o total JÁ refeito, e é dele que o teclado desenha o
      // restante e o troco. Recalcular no terminal faria a tela mostrar um
      // número e a venda cobrar outro.
      setState(() {
        activeOrder = Map<String, dynamic>.from(atualizado);
        couponCode.text = '${atualizado['coupon_code'] ?? ''}';
        couponBusy = false;
        _valorSugeridoDoNovoTotal();
      });
    } on ApiException catch (falha) {
      if (!mounted) return;
      // A RECUSA FICA NO CAMPO, e não no centro de erros: a frase do servidor é
      // sobre o cupom ("Este CPF já usou este cupom") e quem precisa lê-la está
      // olhando o campo que acabou de digitar.
      setState(() {
        couponError = falha.message;
        couponBusy = false;
      });
    } catch (falha) {
      if (!mounted) return;
      setState(() {
        couponError = '$falha';
        couponBusy = false;
      });
    }
  }

  /// O cupom no ALTO do resumo: um seletor com busca (`CouponSelect`).
  ///
  /// Eram campo, botão e uma fileira de botões com os cupons soltos — três
  /// controles para uma escolha, e a fileira empurrava o resumo da conta.
  Widget _couponControl(BuildContext context) => CouponSelect(
    api: api,
    accessToken: token,
    aplicado: _appliedCoupon,
    busy: couponBusy,
    erro: couponError,
    onAplicar: _aplicarCupom,
    onRemover: () => _aplicarCupom(''),
  );

  /// "Cupom NATAL10  - R$ 6,00" entre as parcelas do total.
  ///
  /// Usa `_paymentSummaryRow` de propósito: é uma parcela como as outras, e
  /// um estilo próprio a faria desalinhar de "Desconto" logo acima.
  Widget _couponSummaryRow() {
    final aplicado = _appliedCoupon;
    if (aplicado.isEmpty) return const SizedBox.shrink();
    return _paymentSummaryRow(
      'Cupom $aplicado',
      '- ${_money(_couponDiscount)}',
    );
  }
}
