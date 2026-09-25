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
      final atualizado = await api.post(
        '/orders/${activeOrder!['id']}/apply-coupon/',
        body: {'code': codigo},
        accessToken: token,
      );
      if (!mounted) return;
      // O pedido volta com o total JÁ refeito, e é dele que o teclado desenha o
      // restante e o troco. Recalcular no terminal faria a tela mostrar um
      // número e a venda cobrar outro.
      setState(() {
        activeOrder = Map<String, dynamic>.from(atualizado);
        couponCode.text = '${atualizado['coupon_code'] ?? ''}';
        couponBusy = false;
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

  /// O bloco do cupom no resumo do pagamento.
  ///
  /// A linha "Cupom NATAL10  - R$ 6,00" usa `_paymentSummaryRow` de propósito:
  /// ela é uma parcela do total, e um estilo próprio a faria desalinhar de
  /// "Desconto" logo acima. O campo em si é `PaymentCouponInput`, que vive fora
  /// desta biblioteca porque é a parte que dá para verificar sozinha.
  Widget _couponControl(BuildContext context) {
    final aplicado = _appliedCoupon;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (aplicado.isNotEmpty)
          _paymentSummaryRow('Cupom $aplicado', '- ${_money(_couponDiscount)}'),
        Padding(
          padding: const EdgeInsets.only(top: 4, bottom: 2),
          child: PaymentCouponInput(
            controller: couponCode,
            applied: aplicado,
            busy: couponBusy,
            error: couponError,
            onSubmit: _aplicarCupom,
            onRemove: () {
              couponCode.clear();
              _aplicarCupom('');
            },
          ),
        ),
      ],
    );
  }
}
