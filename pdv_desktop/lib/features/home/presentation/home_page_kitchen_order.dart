// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Cancelar o PEDIDO inteiro, e mandar a rodada para a produção.
///
/// Separado de `home_page_kitchen.dart`, que cuida do item: são decisões de
/// peso diferente. Tirar um prato da conta é do operador; cancelar a venda
/// inteira é de quem responde pelo caixa.
mixin _KitchenOrderSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  List<Map<String, dynamic>> get orderItems;

  Future<void> _goHome();
  Future<void> _refreshOrder();

  Future<void> _cancelOrder() async {
    final order = activeOrder;
    if (order == null ||
        const {
          'paid',
          'cancelled',
          'refunded',
        }.contains('${order['status']}')) {
      return;
    }

    final reason = await ItemVoidReasonDialog.show(
      context,
      itemName: 'Pedido #${order['sequence']}',
      title: 'Cancelar pedido',
      confirmLabel: 'Continuar',
    );
    if (!mounted || reason == null) return;

    Map<String, dynamic>? cancelled;
    if (widget.controller.session!.user.canCancelOrders) {
      // A permissão já veio no perfil autenticado e o servidor a confirma no
      // mesmo request. Não há motivo para pedir uma segunda credencial.
      cancelled = await _work(
        () => api.post(
          '/orders/${order['id']}/cancel/',
          body: {'reason': reason},
          accessToken: token,
        ),
        errorTitle: 'Não foi possível cancelar o pedido',
      );
    } else {
      // Só a senha de ações do caixa: conferida aqui, contra o hash já
      // sincronizado, e enviada ao servidor junto do cancelamento (que é
      // quem apaga consumo já lançado).
      String? cashPassword;
      final authorized = await showSupervisorCloseDialog(
        context: context,
        title: 'Autorizar cancelamento',
        description:
            'Informe a senha de ações do caixa para cancelar este pedido.',
        confirmLabel: 'Cancelar pedido',
        cancelLabel: 'Voltar',
        confirmIcon: Icons.cancel_outlined,
        verifyPassword: (password) async {
          final valid = await widget.controller.verifySupervisorClosePassword(
            password,
          );
          if (valid) cashPassword = password;
          return valid;
        },
        onInvalidPassword: () => widget.controller.syncSupervisorPassword(
          restaurantId: restaurantId,
          force: true,
        ),
      );
      if (!mounted ||
          !authorized ||
          '${activeOrder?['id']}' != '${order['id']}') {
        return;
      }
      cancelled = await _work(
        () => api.post(
          '/orders/${order['id']}/cancel/',
          body: {'reason': reason, 'cash_password': ?cashPassword},
          accessToken: token,
        ),
        errorTitle: 'Não foi possível cancelar o pedido',
      );
    }
    if (!mounted || cancelled == null) return;

    if (!mounted) return;
    await _goHome();
  }

  /// Envia os itens pendentes para produção.
  ///
  /// Quem monta a comanda e decide em qual impressora de setor ela sai é o
  /// SERVIDOR (`register_kitchen_batch_print_jobs`). Este terminal recebe o
  /// `PrintJob` pronto pelo agente e põe no papel — ele é o dono da
  /// impressora, não do documento.
  ///
  /// `client_batch_serial` continua indo: é ele que identifica a rodada e
  /// impede que um reenvio, depois de uma resposta perdida no caminho, gere
  /// uma segunda comanda para os mesmos itens.
  Future<Map<String, dynamic>> _sendPendingItemsToKitchen(
    List<Map<String, dynamic>> pendingItems,
  ) async {
    final batchSerial = OrderPresenter.generateBatchSerial();
    final response = await api.post(
      '/orders/${activeOrder!['id']}/send-to-kitchen/',
      body: {'client_batch_serial': batchSerial},
      accessToken: token,
    );
    AppLogger.instance.info(
      'comanda_envio',
      data: {
        'pedido': '${activeOrder?['id']}',
        'itens_pendentes': pendingItems.length,
        'lote': batchSerial,
      },
    );
    return response;
  }
}
