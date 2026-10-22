// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela.
// ignore_for_file: unused_element

part of 'home_page.dart';

/// Taxa, desconto e CPF da venda NOVA ajustados AQUI, sem ir ao servidor.
///
/// Cada toque simulava a venda inteira no servidor (60 a 120 consultas) com a
/// tela travada em "Calculando total". A conta é a do servidor
/// (`fechamento_local.dart`), e ele confere o total na conclusão. O cupom
/// continua indo ao servidor: só o banco sabe limite, uso por CPF e grupo.
/// O pedido da tela e o fechamento da venda nova, para o Esc voltar a eles.
typedef FotoDoFechamento = ({
  Map<String, dynamic>? pedido,
  Map<String, dynamic>? fechamento,
});

mixin _AjusteLocalSection on _HomePageShared {
  // ── fornecido por `_HomePageState` e pelas outras seções ────────────────
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedRestaurant;
  set adjustError(String value);
  String? get discountPassword;
  set discountPassword(String? value);
  Future<String?> _autorizarDesconto(String motivo);
  void _valorSugeridoDoNovoTotal();
  void _descartarConfirmacao();
  CalculoDoTotal get calculoDoTotal;
  TextEditingController get couponCode;

  /// A taxa padrão do restaurante, como o servidor a aplica no fechamento.
  String get _percentualDaTaxa =>
      '${selectedRestaurant?['default_service_fee_percent'] ?? '0'}';

  /// Aplica `fechamento` na tela na hora; recusa com a frase do servidor.
  Future<void> _ajustarAqui(
    Map<String, dynamic> fechamento, {
    String? senha,
  }) async {
    final pedido = activeOrder;
    if (pedido == null) return;
    // Desconto NOVO de quem não é gerente: a senha de ações do caixa,
    // conferida aqui como no servidor — que confere de novo na conclusão.
    final desconto = centavos(fechamento['discount']);
    final descontoNovo =
        desconto > 0 && desconto != centavos(pedido['discount']);
    var senhaUsada = senha ?? discountPassword;
    if (descontoNovo &&
        senhaUsada == null &&
        !aprovaOProprioDesconto(widget.controller.session!.user)) {
      senhaUsada = await _autorizarDesconto(
        'O desconto precisa da aprovação de um gerente: informe a senha de '
        'ações do caixa.',
      );
      if (!mounted) return;
      if (senhaUsada == null) {
        setState(
          () => adjustError =
              'Desconto não aplicado: ele precisa da aprovação de um gerente.',
        );
        return;
      }
    }
    final antes = _fotoDoFechamento();
    final Map<String, dynamic> atualizado;
    try {
      atualizado = FechamentoLocal.aplicar(
        pedido,
        fechamento,
        percentualDaTaxa:
            '${pedido['service_fee_percent'] ?? _percentualDaTaxa}',
      );
    } on FechamentoRecusado catch (recusa) {
      setState(() => adjustError = recusa.motivo);
      return;
    }
    _descartarConfirmacao();
    setState(() {
      draft.fechamento = fechamento;
      if (descontoNovo) discountPassword = senhaUsada;
      activeOrder = atualizado;
      adjustError = '';
      _valorSugeridoDoNovoTotal();
    });
    _empilharVoltaDoFechamento(antes, 'Ajuste do pagamento');
  }

  /// O fechamento da venda nova como está agora: o pedido da tela e o que vai
  /// na conclusão. Voltar a ele é o Esc de um cupom ou de um ajuste.
  FotoDoFechamento _fotoDoFechamento() =>
      (pedido: activeOrder, fechamento: draft.fechamento);

  void _empilharVoltaDoFechamento(FotoDoFechamento antes, String rotulo) {
    draft.desfazer.empilhar('payment', rotulo, () {
      if (!mounted || antes.pedido == null) return;
      calculoDoTotal.descartar();
      setState(() {
        activeOrder = antes.pedido;
        draft.fechamento = antes.fechamento;
        couponCode.text = '${antes.pedido!['coupon_code'] ?? ''}';
        adjustError = '';
        _valorSugeridoDoNovoTotal();
      });
    });
  }
}
