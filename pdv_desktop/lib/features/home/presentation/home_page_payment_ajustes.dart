// Ver `home_page.dart` para o motivo deste ignore na biblioteca.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Taxa de serviço, CPF/CNPJ e desconto mudados NA TELA DE PAGAMENTO.
///
/// Eram escolhidos num modal antes dela, sem o caixa ver o total — e mudar
/// depois exigia voltar e refazer o fechamento. Agora cada mudança vai ao
/// servidor na hora e o total se redesenha, como já fazia o cupom
/// (`_PaymentCouponSection`):
///
/// * venda nova (prévia simulada): o fechamento muda no rascunho e o servidor
///   recalcula SEM gravar — tudo sobe junto na conclusão;
/// * pedido que já existe: o `/close/` de novo, que aceita fechar outra vez.
///
/// QUEM DECIDE O TOTAL É O SERVIDOR: taxa, desconto e cupom interagem
/// (promoção, teto do cupom), e recalcular aqui mostraria um número e
/// cobraria outro.
mixin _PaymentAdjustSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  List<Map<String, dynamic>> get registeredPayments;
  TextEditingController get paymentDocument;
  double get defaultServiceFeePercent;
  bool get adjustBusy;
  CalculoDoTotal get calculoDoTotal;
  bool get _calculandoTotal;
  set adjustBusy(bool value);
  String get adjustError;
  set adjustError(String value);

  /// A senha que aprovou o desconto desta venda: só em memória, e só até a
  /// venda terminar. A conclusão da venda nova a leva de novo.
  String? get discountPassword;
  set discountPassword(String? value);
  Future<String?> _autorizarDesconto(String motivo);
  void _refreshSuggestedPaymentAmount();
  void _valorSugeridoDoNovoTotal();
  Widget _paymentSummaryRow(String label, String value, {bool strong});

  /// As escolhas que o pedido carrega AGORA — a base de toda mudança.
  Map<String, dynamic> _fechamentoAtual() {
    final pedido = activeOrder ?? const {};
    return {
      'discount': pedido['discount'] ?? 0,
      'service_fee_enabled': pedido['service_fee_enabled'] != false,
      'fiscal_customer_cpf': cpfDigits(pedido['fiscal_customer_cpf']),
      'fiscal_customer_cnpj': cnpjDigits(pedido['fiscal_customer_cnpj']),
      'coupon_code': '${pedido['coupon_code'] ?? ''}'.trim(),
      ...?draft.fechamento,
    };
  }

  /// Aplica `mudanca` sobre o fechamento atual e redesenha com o do servidor.
  Future<void> _ajustarFechamento(
    Map<String, dynamic> mudanca, {
    String? senha,
  }) async {
    if (_calculandoTotal || activeOrder == null) return;
    setState(() {
      adjustBusy = true;
      adjustError = '';
    });
    final fechamento = {..._fechamentoAtual(), ...mudanca};
    final senhaUsada = senha ?? discountPassword;
    final simulada = draft.simulada;
    final pedidoId = activeOrder!['id'];
    Object? recusa;
    await calculoDoTotal.rodar<Map<String, dynamic>>(
      calcular: () async => Map<String, dynamic>.from(
        simulada
            ? await OrderDraftMaterializer(api, accessToken: token).simular(
                draft,
                restaurantId: restaurantId,
                fechamento: fechamento,
                senhaDoCaixa: senhaUsada,
              )
            // Sem `coupon_code`: o cupom tem rota própria, e omiti-lo aqui é
            // "não mexe" — reenviá-lo poderia reavaliar um cupom já aceito.
            : await api.post(
                '/orders/$pedidoId/close/',
                body: {
                  ...fechamento..remove('coupon_code'),
                  'cash_password': ?senhaUsada,
                },
                accessToken: token,
              ),
      ),
      aplicar: (atualizado) {
        if (simulada) draft.fechamento = fechamento;
        if (senha != null) discountPassword = senha;
        if (!mounted) return;
        setState(() {
          activeOrder = atualizado;
          adjustBusy = false;
          _valorSugeridoDoNovoTotal();
        });
      },
      falhar: (erro) => recusa = erro,
    );
    final falha = recusa;
    if (falha == null || !mounted) return;
    setState(() => adjustBusy = false);
    // 403 no desconto: um gerente precisa aprovar. Quem não é gerente libera
    // com a senha de ações do caixa, como no cancelamento.
    if (falha is ApiException &&
        falha.statusCode == 403 &&
        senha == null &&
        mudanca.containsKey('discount')) {
      final liberada = await _autorizarDesconto(falha.message);
      if (liberada != null && mounted) {
        return _ajustarFechamento(mudanca, senha: liberada);
      }
      if (mounted) {
        setState(
          () => adjustError =
              'Desconto não aplicado: ele precisa da aprovação de um gerente.',
        );
      }
      return;
    }
    // Recusado, o total fica o anterior: nada do que foi pedido entrou.
    setState(
      () => adjustError = falha is ApiException ? falha.message : '$falha',
    );
  }

  Future<void> _ajustarDocumento(String digitos) => _ajustarFechamento({
    'fiscal_customer_cpf': digitos.length == 11 ? digitos : '',
    'fiscal_customer_cnpj': digitos.length == 14 ? digitos : '',
  });

  /// "CPF na nota  529.982.247-25" entre as linhas do resumo: confirma o
  /// documento digitado à direita, abaixo do teclado.
  Widget _documentoSummaryRow() {
    final pedido = activeOrder ?? const {};
    final cpf = cpfDigits(pedido['fiscal_customer_cpf']);
    final cnpj = cnpjDigits(pedido['fiscal_customer_cnpj']);
    if (cpf.isEmpty && cnpj.isEmpty) return const SizedBox.shrink();
    return _paymentSummaryRow(
      cpf.isNotEmpty ? 'CPF na nota' : 'CNPJ na nota',
      cpf.isNotEmpty ? formatCpf(cpf) : formatCnpj(cnpj),
    );
  }

  /// O bloco abaixo do teclado: taxa, CPF/CNPJ e desconto.
  Widget _ajustesControl(BuildContext context) {
    final pedido = activeOrder ?? const {};
    final percentual = defaultServiceFeePercent;
    final taxa = _number(pedido['subtotal']) * percentual / 100;
    final cpf = cpfDigits(pedido['fiscal_customer_cpf']);
    return PaymentAdjustments(
      cobrarTaxa: pedido['service_fee_enabled'] != false,
      rotuloTaxa: percentual > 0
          ? '${percentual.toStringAsFixed(percentual % 1 == 0 ? 0 : 2).replaceAll('.', ',')}%'
                ' · ${_money(taxa)}'
          : 'sem taxa configurada no restaurante',
      documento: cpf.isNotEmpty
          ? cpf
          : cnpjDigits(pedido['fiscal_customer_cnpj']),
      documentoControle: paymentDocument,
      descontoCentavos: centavosDe(pedido['discount']),
      maxDescontoCentavos: centavosDe(pedido['subtotal']),
      // Trava também enquanto o CUPOM recalcula: um cálculo por vez.
      busy: _calculandoTotal,
      // Com recebimento lançado, mudar o total deixaria o recebido diferente
      // da conta: remove-se o pagamento primeiro.
      bloqueado: registeredPayments.isNotEmpty,
      erro: adjustError,
      onTaxa: (cobrar) => _ajustarFechamento({'service_fee_enabled': cobrar}),
      onDocumento: _ajustarDocumento,
      onDesconto: (centavos) =>
          _ajustarFechamento({'discount': centavosParaApi(centavos)}),
    );
  }
}
