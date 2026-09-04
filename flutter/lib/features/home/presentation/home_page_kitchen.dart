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
  LocalOrderStore get orderStore;
  TerminalTopology get topology;

  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get selectedCustomer;
  List<Map<String, dynamic>> get orderItems;
  String? get selectedOrderItemId;
  set selectedOrderItemId(String? value);
  bool get isSecondaryStation;

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
      final response = await api.delete(
        '/orders/${activeOrder!['id']}/items/${item['id']}/void/',
        body: {'reason': reason},
        accessToken: token,
      );
      // Item que já estava na produção precisa de cupom no setor para a
      // cozinha parar de fazê-lo. Quem imprime segue a mesma regra da comanda:
      // se a operação subiu, o backend cria o `PrintJob`; se ficou na fila,
      // quem imprime é este terminal — senão o prato continuaria sendo feito
      // depois de o cliente desistir.
      if (inProduction) {
        await _printCancellationIfQueued(item, reason, response);
      }
      await _refreshOrder();
    });
  }

  /// Quem imprime é o servidor (ou o Caixa Principal, pelo relay)?
  ///
  /// Só quando a operação chega ao destino dentro da janela: aí o `PrintJob`
  /// existe lá e sair papel aqui dobraria o cupom.
  ///
  /// **Um Caixa Secundário nunca espera essa janela.** A impressora é dele, o
  /// cupom ele sabe montar, e o cliente está na frente dele — mandar a
  /// impressão para o Principal faria o papel sair na outra ponta da loja. Ele
  /// vai direto reivindicar e imprimir; se a operação já tiver subido, a
  /// reivindicação falha e o backend assume, que é a mesma rede de segurança
  /// de sempre.
  Future<bool> _serverPrintsInstead(String operationId) async {
    if (isSecondaryStation) return false;
    return api.awaitDelivery(
      operationId,
      timeout: api.syncStatus.hasConnection
          ? const Duration(seconds: 3)
          : const Duration(milliseconds: 400),
    );
  }

  /// Imprime o cupom de cancelamento aqui quando a operação não chegou ao
  /// servidor.
  ///
  /// Reivindica a impressão marcando o corpo AINDA enfileirado antes de mandar
  /// papel: se a operação subir nesse instante, a marcação falha e quem
  /// imprime é o backend. É a mesma trava que impede a comanda de cozinha de
  /// sair duas vezes.
  Future<void> _printCancellationIfQueued(
    Map<String, dynamic> item,
    String reason,
    Map<String, dynamic> response,
  ) async {
    final operationId = '${response['_sync_operation_id'] ?? ''}';
    if (operationId.isEmpty) return;
    if (await _serverPrintsInstead(operationId)) return;
    if (!await api.patchQueuedBody(operationId, {'offline_printed': true})) {
      return;
    }
    final printed = await _printCancellationTicket(item, reason);
    if (!printed) {
      await api.patchQueuedBody(operationId, {'offline_printed': false});
    }
  }

  /// Monta e imprime o cupom de cancelamento nas impressoras do setor do
  /// produto. Devolve `true` se pelo menos uma aceitou.
  Future<bool> _printCancellationTicket(
    Map<String, dynamic> item,
    String reason,
  ) async {
    final order = activeOrder;
    if (order == null) return false;
    final text = LocalPrintRenderer.cancellationTicket(
      order: order,
      item: item,
      reason: reason,
      table: selectedTable,
      command: selectedCommand,
      operatorName: widget.controller.session?.user.name ?? '',
    );
    final product = products.cast<Map<String, dynamic>?>().firstWhere(
      (candidate) => '${candidate?['id']}' == '${item['product']}',
      orElse: () => null,
    );
    final sector = '${product?['sector'] ?? ''}';
    var printed = false;
    for (final printer in await _list(
      '/printers/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    )) {
      // Mesma regra da comanda: o cupom sai no setor que recebeu o item. Um
      // produto sem setor, ou um setor sem impressora, simplesmente não gera
      // cupom — sem erro, como no backend.
      if (sector.isEmpty || '${printer['sector'] ?? ''}' != sector) continue;
      try {
        // O cupom entra na fila local: mesmo que esta impressora esteja sem
        // papel agora, ele sai quando ela voltar.
        final cancelPrinter = KitchenCancelPrinter(
          PrinterDevice.fromJson(printer),
          runtime: deviceAgent.printing,
        );
        if ((await deviceAgent.submit(
          cancelPrinter,
          cancelPrinter.compose(content: text),
        )).accepted) {
          printed = true;
        }
      } catch (_) {
        // Outra impressora do setor ainda pode aceitar.
      }
    }
    return printed;
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

    String? cashPassword;
    String? authorizationUsername;
    String? authorizationPassword;
    final authorized = await showSupervisorCloseDialog(
      context: context,
      title: 'Autorizar cancelamento',
      description:
          'Confirme com a senha de operação do restaurante ou com o login '
          'de um administrador/usuário que tenha permissão para cancelar pedidos.',
      confirmLabel: 'Cancelar pedido',
      cancelLabel: 'Voltar',
      confirmIcon: Icons.cancel_outlined,
      credentialRoleLabel: 'usuário autorizado',
      verifyPassword: (password) async {
        final valid = await widget.controller.verifySupervisorClosePassword(
          password,
        );
        if (valid) cashPassword = password;
        return valid;
      },
      verifyAdminCredentials: (username, password) async {
        final failure = await widget.controller
            .verifyOrderCancellationCredentials(username, password);
        if (failure == null) {
          authorizationUsername = username;
          authorizationPassword = password;
        }
        return failure;
      },
      onInvalidPassword: () => widget.controller.refreshSupervisorPassword(
        restaurantId: restaurantId,
      ),
    );
    if (!mounted ||
        !authorized ||
        '${activeOrder?['id']}' != '${order['id']}') {
      return;
    }

    final cancelled = await _work(
      () => api.post(
        '/orders/${order['id']}/cancel/',
        body: {
          'reason': reason,
          'cash_password': ?cashPassword,
          'authorization_username': ?authorizationUsername,
          'authorization_password': ?authorizationPassword,
        },
        accessToken: token,
      ),
      errorTitle: 'Não foi possível cancelar o pedido',
    );
    if (!mounted || cancelled == null) return;

    final scope = api.sessionScope;
    if (scope != null) {
      await orderStore.saveFromServer(cancelled, scope: scope);
    }
    if (!mounted) return;
    await _goHome();
  }

  /// Envia os itens pendentes para produção. Quando a rede está fora, imprime
  /// a comanda direto na impressora do setor em vez de esperar o backend
  /// renderizar o `PrintJob` — a cozinha não pode esperar a internet voltar
  /// pra saber que tem pedido novo.
  ///
  /// `offline_printed` só acompanha o envio se a comanda tiver saído mesmo:
  /// essa flag faz o backend registrar os `PrintJob` como já impressos, então
  /// mandá-la depois de uma impressão que falhou deixaria a cozinha sem
  /// comanda nenhuma — nem agora, nem quando a fila sincronizasse.
  ///
  /// A condição é `phase == offline`, e não "sem conexão": `unknown` (antes da
  /// primeira resposta) e `degraded` (servidor instável, mas respondendo)
  /// também contam como "sem conexão" e levavam a imprimir aqui um pedido que
  /// o backend ia imprimir de novo — duas comandas para a mesma rodada.
  Future<Map<String, dynamic>> _sendPendingItemsToKitchen(
    List<Map<String, dynamic>> pendingItems,
  ) async {
    final batchSerial = OrderPresenter.generateBatchSerial();
    final response = await api.post(
      '/orders/${activeOrder!['id']}/send-to-kitchen/',
      body: {'client_batch_serial': batchSerial},
      accessToken: token,
    );
    final operationId = '${response['_sync_operation_id'] ?? ''}';
    AppLogger.instance.info(
      'comanda_envio',
      data: {
        'pedido': '${activeOrder?['id']}',
        'itens_pendentes': pendingItems.length,
        'lote': batchSerial,
        'na_fila': operationId.isNotEmpty,
        'conexao': api.syncStatus.phase.name,
      },
    );
    // Sem operação na fila, quem executou foi o servidor (ou o Caixa
    // Principal, num caixa secundário): o `PrintJob` já existe lá.
    if (operationId.isEmpty) {
      AppLogger.instance.info(
        'comanda_impressao_do_servidor',
        data: {'motivo': 'operacao entregue direto, o PrintJob e de la'},
      );
      return response;
    }

    // Quem imprime a comanda não pode ser decidido por um palpite sobre a
    // conexão. Antes a escolha era feita ANTES do POST, olhando o último
    // estado conhecido da rede; com o PDV offline-first toda escrita passa
    // pela fila, e um estado velho levava aos dois piores resultados
    // possíveis: duas comandas para a mesma rodada, ou nenhuma. Agora a
    // pergunta é factual — a operação chegou ao servidor?
    // Com a rede de pé, três segundos são de sobra para a fila entregar. Com
    // ela reconhecidamente fora, esperar tanto só atrasaria a cozinha — mas a
    // pergunta continua sendo feita, porque o indicador pode estar um
    // instante atrás da realidade.
    if (await _serverPrintsInstead(operationId)) {
      AppLogger.instance.info(
        'comanda_impressao_do_servidor',
        data: {
          'motivo': 'a operacao subiu dentro da janela',
          'operacao': operationId,
        },
      );
      return response;
    }

    // Ela continua na fila. Reivindica a impressão marcando o corpo ANTES de
    // imprimir: se a operação subir neste instante, a marcação falha e quem
    // imprime é o backend. Sem isso, a janela entre imprimir e marcar deixava
    // sair a segunda comanda.
    final claimed = await api.patchQueuedBody(operationId, {
      'offline_printed': true,
    });
    if (!claimed) {
      AppLogger.instance.info(
        'comanda_impressao_do_servidor',
        data: {
          'motivo': 'a operacao subiu enquanto este terminal reivindicava',
          'operacao': operationId,
        },
      );
      return response;
    }

    final printed = await _printKitchenTicketsOffline(
      pendingItems,
      batchSerial,
    );
    if (!printed) {
      AppLogger.instance.warning(
        'comanda_devolvida_ao_backend',
        data: {
          'operacao': operationId,
          'motivo': 'nenhuma impressora aceitou o cupom neste terminal',
        },
      );
      // Não saiu papel aqui. Devolve a impressão ao backend, senão a cozinha
      // ficaria sem comanda agora e também quando a fila sincronizasse.
      await api.patchQueuedBody(operationId, {'offline_printed': false});
    }
    return response;
  }

  /// Monta e imprime a comanda localmente. Devolve `true` se pelo menos uma
  /// impressora aceitou o cupom.
  Future<bool> _printKitchenTicketsOffline(
    List<Map<String, dynamic>> pendingItems,
    String batchSerial,
  ) async {
    // As impressoras vêm da lista que o agente mantém em memória: reler
    // `/printers/` aqui só funcionaria se aquela consulta exata já estivesse
    // no cache de respostas, o que não se pode assumir com a rede fora.
    final printersForTickets = await deviceAgent.ensurePrinters();
    final user = widget.controller.session?.user;
    final plan = OrderPresenter.buildOfflineKitchenTickets(
      order: activeOrder,
      table: selectedTable,
      command: selectedCommand,
      pendingItems: pendingItems,
      products: products,
      printers: printersForTickets,
      batchSerial: batchSerial,
      operatorName: (user?.name ?? '').trim().isNotEmpty
          ? user!.name
          : (user?.username ?? ''),
    );
    final tickets = plan.tickets;
    // A escolha da impressora pelo setor do produto é silenciosa por
    // natureza: item sem setor e setor sem impressora não geram papel nem
    // erro. Esta linha é o que transforma "não imprimiu e não avisou" em algo
    // que se lê no terminal.
    AppLogger.instance.info('comanda_roteamento', data: plan.toLog());
    var printedAny = false;
    Object? lastFailure;
    for (final ticket in tickets) {
      try {
        // Pela fila local: uma impressora sem papel agora não perde a
        // comanda — ela sai assim que o papel voltar, sem depender de um
        // evento do servidor que, offline, nunca chega.
        // `accepted`, não `printed`: com o cupom na fila, este terminal já é
        // o responsável — mesmo que a impressora só aceite daqui a pouco.
        final kitchenPrinter = KitchenPrinter(
          PrinterDevice.fromJson(ticket.printer),
          runtime: deviceAgent.printing,
        );
        if ((await deviceAgent.submit(
          kitchenPrinter,
          kitchenPrinter.compose(content: ticket.text),
        )).accepted) {
          printedAny = true;
        }
      } catch (error) {
        // Uma impressora falhar não pode travar as outras.
        lastFailure = error;
      }
    }
    if (!mounted || printedAny) return printedAny;
    // A mensagem precisa dizer o que de fato impediu a impressão: culpar a
    // internet quando o problema é roteamento de setor manda o caixa
    // procurar no lugar errado.
    showAppToast(
      context,
      switch ((tickets.isEmpty, lastFailure)) {
        (true, _) =>
          'Nenhuma impressora de setor atende os itens deste pedido. '
              'Confira o setor dos produtos e o setor das impressoras em '
              'Configurações e avise a cozinha manualmente.',
        (false, final failure?) =>
          'A comanda não pôde ser enviada à impressora do setor: $failure. '
              'Avise a cozinha manualmente.',
        _ =>
          'A comanda não pôde ser impressa agora. Avise a cozinha '
              'manualmente.',
      },
      title: 'Comanda não impressa',
      severity: AppErrorSeverity.warning,
    );
    return false;
  }
}
