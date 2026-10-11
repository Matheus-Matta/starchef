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

  /// O total OFICIAL da venda, sem criá-la: a tela de pagamento abre sobre o
  /// pedido que o servidor CALCULOU (taxa, promoção, cupom), e ele só nasce na
  /// conclusão, com os recebimentos, num envio só.
  @override
  Future<bool> _simularVenda() async {
    if (draft.isEmpty) return false;
    final previa = await _workResolvendo(
      () => OrderDraftMaterializer(api, accessToken: token).simular(
        draft,
        restaurantId: restaurantId,
        fechamento: draft.fechamento,
      ),
      errorTitle: 'Não foi possível calcular o pedido',
    );
    if (previa == null || !mounted) return false;
    setState(() {
      draft.simulada = true;
      // A partir daqui a venda é ESTA: a conclusão leva só estas anotações.
      draft.anotacoesVistas ??= [
        for (final item in _itensDe(previa))
          if (item['command_item'] != null) '${item['command_item']}',
      ];
      activeOrder = previa;
      orderItems = _itensDe(previa);
      selectedCommand = draft.command;
      selectedTable = draft.table;
      selectedCustomer = draft.customer;
      orderType = draft.orderType;
    });
    return true;
  }

  /// Saiu da tela de pagamento sem pagar: nada foi criado, o rascunho volta.
  @override
  void _desfazerSimulacao() {
    if (!draft.simulada) return;
    draft.simulada = false;
    draft.fechamento = null;
    draft.anotacoesVistas = null;
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
    final resposta = await _workResolvendo(
      () => OrderDraftMaterializer(api, accessToken: token).concluir(
        draft,
        restaurantId: restaurantId,
        fechamento: draft.fechamento,
        recebimentos: recebimentos,
        totalMostrado: activeOrder?['total'] == null
            ? null
            : '${activeOrder!['total']}',
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
    return true;
  }

  static List<Map<String, dynamic>> _itensDe(Map<String, dynamic> pedido) => [
    for (final item in pedido['items'] as List? ?? const [])
      Map<String, dynamic>.from(item as Map),
  ];
}
