// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Cozinha e cancelamento: cancelar item ou pedido, o cupom que avisa a
/// produção, e o envio da rodada.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _KitchenSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get selectedCustomer;
  Map<String, dynamic>? get selectedRestaurant;
  List<Map<String, dynamic>> get orderItems;
  String? get selectedOrderItemId;
  set selectedOrderItemId(String? value);

  Future<void> _goHome();
  List<Map<String, dynamic>> get products;
  Future<void> _refreshOrder();

  Future<void> _voidItem(Map<String, dynamic> item) async {
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
      await api.delete(
        '/orders/${activeOrder!['id']}/items/${item['id']}/void/',
        body: {'reason': reason},
        accessToken: token,
      );
      // O cupom de cancelamento é criado pelo servidor junto com a baixa do
      // item (`register_kitchen_item_cancellation_jobs`). O agente deste
      // terminal recebe o `PrintJob` no ciclo seguinte e põe no papel: não há
      // nada a imprimir daqui, e imprimir dobraria o cupom no setor.
      await _refreshOrder();
    });
  }

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

    // Carência do restaurante: dentro dela nada chegou à produção e o
    // servidor cancela sem senha. Quem sabe se ainda está dentro é ele (o
    // relógio da rodada é de lá), então a primeira tentativa vai sem senha;
    // um 403 é "já saiu da carência" e aí a senha é pedida como sempre.
    Map<String, dynamic>? cancelled;
    final graceConfigured =
        _number(selectedRestaurant?['cancellation_grace_seconds']).round() > 0;
    if (graceConfigured) {
      try {
        cancelled = await api.post(
          '/orders/${order['id']}/cancel/',
          body: {'reason': reason},
          accessToken: token,
        );
      } on ApiException catch (error) {
        if (error.statusCode != 403) {
          if (mounted) {
            _error(error, title: 'Não foi possível cancelar o pedido');
          }
          return;
        }
      }
      if (!mounted) return;
    }

    if (cancelled == null) {
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
