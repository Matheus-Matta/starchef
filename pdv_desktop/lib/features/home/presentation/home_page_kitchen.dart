// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Cancelar um ITEM — e a autorização que destrava o que a regra barrou.
///
/// Cancelar o PEDIDO e mandar a rodada para a produção são outros gestos, e
/// moram em `home_page_kitchen_order.dart`: o que muda entre eles não é o
/// código, é quem decide. Tirar um prato da conta é do operador; cancelar a
/// venda inteira é de quem responde pelo caixa.
mixin _KitchenSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get selectedCustomer;
  List<Map<String, dynamic>> get orderItems;
  String? get selectedOrderItemId;
  set selectedOrderItemId(String? value);

  Future<void> _goHome();
  List<Map<String, dynamic>> get products;
  Future<void> _refreshOrder();

  Future<void> _voidItem(Map<String, dynamic> item) async {
    // Linha de rascunho: nada foi lançado, nada foi produzido, e não há o que
    // registrar. Pedir motivo de cancelamento para tirar um item que só
    // existe nesta tela seria burocracia sobre coisa nenhuma.
    if (_draftIsLive) {
      if (item[OrderDraftCart.marcaDeJaLancado] == true) {
        _error(
          const ApiException(
            'Este item já está lançado na comanda e não sai daqui. Para '
            'cancelá-lo, abra o pedido dela.',
          ),
        );
        return;
      }
      _removeDraftLine('${item['id']}');
      if (mounted && '${item['id']}' == selectedOrderItemId) {
        setState(() => selectedOrderItemId = null);
      }
      return;
    }
    // Item já enviado à cozinha: o cancelamento não é só tirar da conta, sai
    // um cupom na impressora do setor para a produção parar. Avisar antes
    // evita o caixa descobrir isso pelo barulho da impressora.
    final inProduction = '${item['status']}' != 'pending';
    final reason = await ItemVoidReasonDialog.show(
      context,
      itemName: '${item['product_name'] ?? 'Item do pedido'}',
      title: inProduction ? 'Cancelar item em produção' : 'Remover item',
      confirmLabel: inProduction ? 'Cancelar e avisar cozinha' : 'Remover item',
      warning: inProduction
          ? 'Este item já foi enviado para a cozinha. Uma nota de '
                'cancelamento será impressa no setor que o recebeu.'
          : null,
    );
    if (reason == null || !mounted) return;

    await _work(() async {
      try {
        await _enviarCancelamentoDeItem(item, reason: reason);
      } on ApiException catch (erro) {
        // 409 é o servidor dizendo que o ESTADO barra: passou do prazo de
        // cancelamento ou o item está numa coluna do KDS que bloqueia. Não é
        // erro de preenchimento — repetir o mesmo corpo não resolve, e existe
        // uma saída: um supervisor libera com a senha de ações do caixa.
        if (erro.statusCode != 409) rethrow;
        final liberado = await _autorizarCancelamentoDeItem(erro.message);
        if (liberado == null) return;
        await _enviarCancelamentoDeItem(
          item,
          reason: reason,
          cashPassword: liberado,
        );
      }
      // O cupom de cancelamento é criado pelo servidor junto com a baixa do
      // item (`register_kitchen_item_cancellation_jobs`). O agente deste
      // terminal recebe o `PrintJob` no ciclo seguinte e põe no papel: não há
      // nada a imprimir daqui, e imprimir dobraria o cupom no setor.
      await _refreshOrder();
    });
  }

  Future<void> _enviarCancelamentoDeItem(
    Map<String, dynamic> item, {
    required String reason,
    String? cashPassword,
  }) => api.delete(
    '/orders/${activeOrder!['id']}/items/${item['id']}/void/',
    body: {'reason': reason, 'cash_password': ?cashPassword},
    accessToken: token,
  );

  /// Pede a senha de ações do caixa para liberar um cancelamento barrado.
  ///
  /// Devolve a senha quando alguém autoriza, ou `null` quando desiste. A senha
  /// é conferida aqui contra o hash já sincronizado E enviada ao servidor, que
  /// é quem de fato decide — conferir só no terminal seria uma tranca que
  /// qualquer cliente desatualizado contorna.
  Future<String?> _autorizarCancelamentoDeItem(String motivo) async {
    String? senha;
    final autorizado = await showSupervisorCloseDialog(
      context: context,
      title: 'Autorizar cancelamento',
      description:
          '$motivo Informe a senha de ações do caixa para liberar.',
      confirmLabel: 'Liberar cancelamento',
      cancelLabel: 'Voltar',
      confirmIcon: Icons.lock_open_outlined,
      verifyPassword: (password) async {
        final valid = await widget.controller.verifySupervisorClosePassword(
          password,
        );
        if (valid) senha = password;
        return valid;
      },
      onInvalidPassword: () => widget.controller.syncSupervisorPassword(
        restaurantId: restaurantId,
        force: true,
      ),
    );
    return autorizado ? senha : null;
  }
}
