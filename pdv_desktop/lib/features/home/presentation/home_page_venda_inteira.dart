part of 'home_page.dart';

/// A venda inteira, do lado do PDV: simular, desfazer e concluir.
///
/// A tela de pagamento abre sobre o pedido que o servidor CALCULOU sem gravar
/// (`simular`), e ele só nasce na conclusão, com os recebimentos, num envio só
/// (`orders/venda_inteira.py`). Separado do fluxo do rascunho porque é um
/// assunto próprio: o que existe no servidor e quando.
mixin _VendaInteiraSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  set selectedCommand(Map<String, dynamic>? value);
  set selectedTable(Map<String, dynamic>? value);
  set selectedCustomer(Map<String, dynamic>? value);
  set orderType(String? value);
  set orderItems(List<Map<String, dynamic>> value);
  set registeredPayments(List<Map<String, dynamic>> value);

  /// A senha que aprovou o desconto na tela de pagamento: a conclusão a leva
  /// de novo, porque a simulação aprovou e desfez (`_PaymentAdjustSection`).
  String? get discountPassword;
  set discountPassword(String? value);

  set flowStep(String value);
  bool get paymentAmountTyped;
  set paymentDigits(String value);
  double get remainingTotal;
  void _syncPaymentAmount();
  void _valorSugeridoDoNovoTotal();
  Future<bool> _resolverConflito(Object erro);

  /// A confirmação, pelo servidor, da prévia aberta na hora
  /// (`previa_local.dart`). A conclusão espera por ela: nunca conclui sobre
  /// a soma local.
  Future<bool>? _confirmacao;

  /// Cada cálculo ganha um número: a resposta de um antigo não sobrescreve a
  /// de um ajuste (taxa, cupom) feito depois na tela de pagamento.
  int _rodadaDaPrevia = 0;

  /// Mostra o pagamento JÁ, com o pedido que o PDV montou, e pede a conta ao
  /// servidor em paralelo. Fora do `_work` de propósito: `busy` trava a tela
  /// inteira, e a tela travada era justamente a espera que isto tira.
  @override
  void _abrirPreviaLocal() {
    final previa = previaLocal(draft);
    draft.simulada = true;
    activeOrder = previa;
    orderItems = _itensDe(previa);
    selectedCommand = draft.command;
    selectedTable = draft.table;
    selectedCustomer = draft.customer;
    orderType = draft.orderType;
    _confirmacao = _confirmarPrevia(++_rodadaDaPrevia);
  }

  Future<bool> _confirmarPrevia(int rodada) async {
    try {
      final previa = await OrderDraftMaterializer(api, accessToken: token)
          .simular(
            draft,
            restaurantId: restaurantId,
            fechamento: draft.fechamento,
          );
      if (!mounted || !draft.simulada) return false;
      if (rodada == _rodadaDaPrevia) setState(() => _aplicarPrevia(previa));
      return true;
    } catch (erro) {
      if (!mounted || rodada != _rodadaDaPrevia) return false;
      // O servidor recusou a venda: volta ao pedido, como se a tela de
      // pagamento nunca tivesse aberto, e resolve a recusa como antes.
      setState(() {
        _desfazerSimulacao();
        flowStep = 'order';
      });
      if (!await _resolverConflito(erro)) {
        _error(erro, title: 'Não foi possível calcular o pedido');
      }
      return false;
    }
  }

  void _aplicarPrevia(Map<String, dynamic> previa) {
    draft.simulada = true;
    // A partir daqui a venda é ESTA: a conclusão leva só estas anotações.
    draft.anotacoesVistas ??= [
      for (final item in _itensDe(previa))
        if (item['command_item'] != null) '${item['command_item']}',
    ];
    final totalAntes = '${activeOrder?['total']}';
    activeOrder = previa;
    orderItems = _itensDe(previa);
    selectedCommand = draft.command;
    selectedTable = draft.table;
    selectedCustomer = draft.customer;
    orderType = draft.orderType;
    // Total diferente do mostrado (taxa, promoção): o valor sugerido vai para
    // o novo. Igual, o que o caixa digitou (um pagamento parcial) fica.
    if (totalAntes != '${previa['total']}') {
      _valorSugeridoDoNovoTotal();
    } else if (!paymentAmountTyped) {
      paymentDigits = (remainingTotal * 100).round().toString();
      _syncPaymentAmount();
    }
  }

  /// O total OFICIAL da venda, sem criá-la: a tela de pagamento abre sobre o
  /// pedido que o servidor CALCULOU (taxa, promoção, cupom), e ele só nasce na
  /// conclusão, com os recebimentos, num envio só.
  @override
  Future<bool> _simularVenda() async {
    if (draft.isEmpty) return false;
    // Um cálculo novo (ajuste na tela) vence o que ainda estava em voo.
    final rodada = ++_rodadaDaPrevia;
    _confirmacao = null;
    final previa = await _workResolvendo(
      () => OrderDraftMaterializer(api, accessToken: token).simular(
        draft,
        restaurantId: restaurantId,
        fechamento: draft.fechamento,
      ),
      errorTitle: 'Não foi possível calcular o pedido',
    );
    if (previa == null || !mounted) return false;
    if (rodada == _rodadaDaPrevia) setState(() => _aplicarPrevia(previa));
    return true;
  }

  /// Saiu da tela de pagamento sem pagar: nada foi criado, o rascunho volta.
  @override
  void _desfazerSimulacao() {
    if (!draft.simulada) return;
    // A confirmação que ainda voltar já não vale para nada na tela.
    _rodadaDaPrevia++;
    _confirmacao = null;
    draft.simulada = false;
    draft.fechamento = null;
    draft.anotacoesVistas = null;
    discountPassword = null;
    activeOrder = null;
    orderItems = [];
  }

  /// A conclusão: pedido, cozinha, fechamento e recebimentos num envio só.
  ///
  /// Falhou, nada foi gravado (é uma transação no servidor): a tela continua
  /// com o rascunho e os recebimentos montados, e o operador tenta de novo —
  /// com os MESMOS UUIDs, então o reenvio nunca duplica.
  @override
  Future<bool> _concluirVendaSimulada(
    List<Map<String, dynamic>> recebimentos,
  ) async {
    // Aberto na hora: conclui só depois de o servidor confirmar o total. O
    // clique espera aqui em vez de se perder (`_work` desiste se ocupado).
    final pendente = _confirmacao;
    if (pendente != null && !await pendente) return false;
    final resposta = await _workResolvendo(
      () => OrderDraftMaterializer(api, accessToken: token).concluir(
        draft,
        restaurantId: restaurantId,
        fechamento: draft.fechamento,
        recebimentos: recebimentos,
        totalMostrado: activeOrder?['total'] == null
            ? null
            : '${activeOrder!['total']}',
        senhaDoCaixa: discountPassword,
      ),
      // O total mudou, a comanda já foi paga: `_ConflitosSection` recalcula
      // ou abre o pedido certo, em vez de só mostrar o erro.
      errorTitle: 'Não foi possível concluir a venda',
    );
    if (resposta == null || !mounted) return false;
    final pedido = Map<String, dynamic>.from(resposta['order'] as Map);
    activeOrder = pedido;
    orderItems = _itensDe(pedido);
    registeredPayments = [
      for (final pagamento in resposta['payments'] as List? ?? const [])
        Map<String, dynamic>.from(pagamento as Map),
    ];
    draft.clear();
    discountPassword = null;
    return true;
  }

  static List<Map<String, dynamic>> _itensDe(Map<String, dynamic> pedido) => [
    for (final item in pedido['items'] as List? ?? const [])
      Map<String, dynamic>.from(item as Map),
  ];
}
