// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// A casca da tela: barra lateral, cabeçalho e o `build` que escolhe o painel
/// da etapa atual.
///
/// O código foi MOVIDO, não reescrito.
mixin _ShellSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;
  PdvUpdateStatus get versionStatus;
  NetworkStatus get networkStatus;
  Map<String, dynamic>? get activeOrder;
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get cashSession;
  List<Map<String, dynamic>> get restaurants;
  List<Map<String, dynamic>> get orderItems;
  String get flowStep;
  set flowStep(String value);

  /// Definido em `home_page_kitchen.dart`: pede a senha do supervisor para
  /// liberar um cancelamento que o servidor barrou.
  Future<String?> _autorizarCancelamentoDeItem(String motivo);
  String? get orderType;
  String? get selectedRestaurantId;
  bool get loading;
  bool get refreshing;
  bool get sidebarExpanded;
  set sidebarExpanded(bool value);
  bool get offlineMode;
  bool get hasCashDivergence;
  bool get _canSeeCashBalance;
  String get _cashBalanceLabel;
  double get remainingTotal;

  Future<void> _load();
  void _goBack();
  Future<void> _goHome();
  Future<void> _navigateTo(PdvDestination destination);
  Future<void> _openCash();
  void _onCashMenuSelected(String value);
  List<PopupMenuEntry<String>> _cashMenuItems();
  PdvDestination get _selectedDestination;
  Future<void> _changeRestaurant(String value);
  Future<void> _checkPdvVersion();
  Future<void> _openHelp();
  Future<void> _openCommand(Map<String, dynamic> command);
  StreamController<String> get commandPageCodes;
  Future<void> _changeScaleRestaurant(String value);
  Map<String, dynamic>? get pendingCashMovement;
  Future<void> _showMovementApproval();
  String? get loadErrorMessage;
  List<Map<String, dynamic>> get products;
  List<Map<String, dynamic>> get categories;
  List<Map<String, dynamic>> get tables;
  Future<void> _seatCommandAtTable();
  Future<void> _unlinkCommandFromTable(Map<String, dynamic> command);
  Widget _sidebarOperationPanel({bool compact});
  (String, String, IconData) get _workspaceIdentity;
  Widget _catalog();
  Widget _cart();
  Widget _ordersPage();
  Widget _paymentPage();
  Widget _tableContextPanel();
  Widget _commandContextPanel();

  /// A linha de apoio da barra: quem é este pedido, em uma linha.
  ///
  /// A regra de como montar essa linha está em [OrderPresenter.headerSubtitle]
  /// — aqui só se junta o que a tela tem em mãos.
  String get _headerSubtitle {
    final order = activeOrder;
    if (order == null) return _workspaceIdentity.$2;
    return OrderPresenter.headerSubtitle(
      order: order,
      table: selectedTable,
      command: selectedCommand,
      itemCount: orderItems.length,
      money: _money,
      remaining: flowStep == 'payment' ? remainingTotal : null,
    );
  }

  String _sidebarUserSubtitle() {
    final user = widget.controller.session!.user;
    final profile = switch (user.profileType) {
      'owner' => 'Proprietário',
      'admin' => 'Administrador',
      'manager' => 'Gerente',
      'cashier' => 'Operador de caixa',
      'waiter' => 'Garçom',
      _ => '',
    };
    final username = user.username.trim();
    if (username.isEmpty) {
      return profile.isEmpty ? 'Usuário conectado' : profile;
    }
    return profile.isEmpty ? '@$username' : '@$username · $profile';
  }

  String get _shiftLabel {
    final opened = DateTime.tryParse('${cashSession?['opened_at'] ?? ''}');
    if (opened == null) return 'Turno não iniciado';
    final local = opened.toLocal();
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return 'Turno desde $hour:$minute';
  }

  String? get _operationalMessage {
    if (activeOrder?['_offline_pending'] == true) {
      return 'Salvo neste caixa — sincronização pendente';
    }
    final printer = deviceAgent.printerAvailability.value;
    if (printer.phase == PrinterAvailabilityPhase.unavailable) {
      return 'Impressora temporariamente indisponível — tentando novamente';
    }
    if (busy) {
      return flowStep == 'payment'
          ? 'Pagamento sendo processado…'
          : 'Processando operação…';
    }
    if (refreshing) return 'Atualizando dados operacionais…';
    return activeOrder == null ? null : _headerSubtitle;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (restaurants.isEmpty) {
      return AppPageScaffold(
        title: 'StarChef PDV',
        description: 'Não foi possível preparar a unidade para atendimento.',
        leading: Padding(
          padding: const EdgeInsets.all(5),
          child: Image.asset('assets/logoicon.png', width: 32, height: 32),
        ),
        actions: [
          IconButton.outlined(
            tooltip: widget.isDark ? 'Usar tema claro' : 'Usar tema escuro',
            onPressed: widget.onToggleTheme,
            icon: Icon(
              widget.isDark
                  ? Icons.light_mode_outlined
                  : Icons.dark_mode_outlined,
            ),
          ),
          IconButton.outlined(
            tooltip: 'Sair',
            onPressed: widget.controller.logout,
            icon: const Icon(Icons.logout),
          ),
        ],
        body: AppEmptyState(
          icon: offlineMode ? Icons.cloud_off : Icons.storefront_outlined,
          title: offlineMode
              ? 'Dados offline ainda não disponíveis'
              : 'Não foi possível carregar os restaurantes',
          description:
              loadErrorMessage ??
              'Conecte o PDV à internet ao menos uma vez para baixar os dados necessários.',
          action: FilledButton.icon(
            onPressed: loading ? null : _load,
            icon: const Icon(Icons.refresh),
            label: const Text('Tentar novamente'),
          ),
        ),
      );
    }
    return Scaffold(
      body: Row(
        children: [
          PdvNavigationRail(
            selected: _selectedDestination,
            onSelected: (destination) => unawaited(_navigateTo(destination)),
            showOrders: widget.controller.session!.user.canViewOrders,
            showFinance: widget.controller.session!.user.canAccessCash,
          ),
          Expanded(
            child: Column(
              children: [
                PdvOperationalBar(
                  cashName: cashSession == null
                      ? 'StarChef PDV'
                      : cashStationLabelOf(cashSession!),
                  operatorName:
                      widget.controller.session!.user.name.trim().isEmpty
                      ? widget.controller.session!.user.username
                      : widget.controller.session!.user.name,
                  shiftLabel: _shiftLabel,
                  cashOpen: cashSession != null,
                  network: networkStatus,
                  printer: deviceAgent.printerAvailability,
                  syncPending:
                      offlineMode || activeOrder?['_offline_pending'] == true,
                  versionStatus: versionStatus,
                  // O sino fica no fim da barra de status, ao lado dos outros
                  // sinais de "como as coisas estão" — o operador olha para um
                  // canto só.
                  //
                  // Ele NÃO é enfeite: desde que só falha interrompe a tela,
                  // sucesso e aviso não têm outro lugar para existir. Sem o
                  // sino montado, "venda concluída" e "impressora indisponível"
                  // são gravados no histórico e nunca vistos por ninguém.
                  trailing: const NotificationBell(),
                ),
                // Logo abaixo da barra de estado e ACIMA do conteúdo: uma
                // mudança de onde a venda é gravada não cabe num selo.
                PdvCloudBanner(visible: networkStatus.servidoPelaNuvem),
                Expanded(
                  child: Stack(
                    children: [
                      if (flowStep == 'scale-workstation')
                        ScaleWorkstationPage(
                          api: api,
                          accessToken: token,
                          restaurants: restaurants,
                          restaurantId: restaurantId,
                          products: products,
                          onRestaurantChanged: _changeScaleRestaurant,
                          preferences: widget.preferences,
                        )
                      else if (flowStep == 'commands')
                        CommandsPage(
                          repository: CommandRepository(
                            api,
                            accessToken: token,
                          ),
                          restaurantId: restaurantId,
                          codigosLidos: commandPageCodes.stream,
                          // A tela de comandas não conhece o controlador; ela
                          // recebe só a capacidade de pedir a liberação.
                          autorizarCancelamento: _autorizarCancelamentoDeItem,
                          // O MESMO catálogo da venda: a tela de comandas
                          // lança produto igual, e carregar uma segunda cópia
                          // faria as duas divergirem na primeira alteração de
                          // cardápio.
                          products: products,
                          categories: categories,
                          tables: tables,
                        )
                      else if (flowStep == 'orders')
                        _ordersPage()
                      else if (activeOrder == null && flowStep == 'context')
                        (orderType == 'command'
                            ? _commandContextPanel()
                            : _tableContextPanel())
                      else if (activeOrder == null &&
                          flowStep == 'table_details' &&
                          selectedTable != null)
                        TableDetailsPanel(
                          table: selectedTable!,
                          onBack: () => setState(() => flowStep = 'context'),
                          onOpenCommand: (cmd) => _openCommand(cmd),
                          onAddCommand: busy ? null : _seatCommandAtTable,
                          onUnlinkCommand: busy
                              ? null
                              : (cmd) =>
                                    unawaited(_unlinkCommandFromTable(cmd)),
                        )
                      else if (flowStep == 'payment')
                        _paymentPage()
                      else
                        LayoutBuilder(
                          builder: (context, constraints) {
                            final cartWidth = constraints.maxWidth < 980
                                ? 360.0
                                : constraints.maxWidth >= 1500
                                ? 400.0
                                : 380.0;
                            return Padding(
                              padding: const EdgeInsets.all(12),
                              child: Row(
                                children: [
                                  Expanded(child: _catalog()),
                                  const SizedBox(width: 12),
                                  SizedBox(width: cartWidth, child: _cart()),
                                ],
                              ),
                            );
                          },
                        ),
                      if (cashSession == null)
                        Positioned.fill(
                          child: ColoredBox(
                            color: scheme.surface.withValues(alpha: .94),
                            child: Center(
                              child: SizedBox(
                                width: 460,
                                child: ShadCard(
                                  radius: AppTheme.radius,
                                  shadows: const [],
                                  child: Padding(
                                    padding: const EdgeInsets.all(32),
                                    child: Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(
                                          Icons.lock_outline,
                                          size: 58,
                                          color: scheme.primary,
                                        ),
                                        const SizedBox(height: 16),
                                        const Text(
                                          'Abra o caixa para iniciar',
                                          style: TextStyle(
                                            fontSize: 24,
                                            fontWeight: FontWeight.w800,
                                          ),
                                        ),
                                        const SizedBox(height: 8),
                                        const Text(
                                          'O PDV só pode registrar pedidos quando o operador possui um caixa vinculado e uma sessão aberta.',
                                          textAlign: TextAlign.center,
                                        ),
                                        const SizedBox(height: 22),
                                        FilledButton.icon(
                                          onPressed: _openCash,
                                          icon: const Icon(Icons.lock_open),
                                          label: const Text('Abrir caixa'),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      if (pendingCashMovement != null && !hasCashDivergence)
                        Positioned(
                          top: 12,
                          left: 24,
                          right: 24,
                          child: Material(
                            color: Colors.orange.shade50,
                            elevation: 3,
                            borderRadius: AppTheme.radius,
                            child: InkWell(
                              borderRadius: AppTheme.radius,
                              onTap: _showMovementApproval,
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 18,
                                  vertical: 13,
                                ),
                                child: Row(
                                  children: [
                                    Icon(
                                      Icons.warning_amber_rounded,
                                      color: Colors.orange.shade900,
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Text(
                                        '${pendingCashMovement!['movement_type'] == 'withdrawal' ? 'Sangria' : 'Suprimento'} de ${_money(_number(pendingCashMovement!['amount']).abs())} aguardando autorização gerencial.',
                                        style: TextStyle(
                                          color: Colors.orange.shade900,
                                          fontWeight: FontWeight.w800,
                                        ),
                                      ),
                                    ),
                                    const Text(
                                      'Resolver agora',
                                      style: TextStyle(
                                        fontWeight: FontWeight.w800,
                                      ),
                                    ),
                                    const SizedBox(width: 6),
                                    const Icon(Icons.chevron_right),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      // Uma barra fina no topo, em vez de cobrir a tela.
                      //
                      // O overlay escuro com spinner central aparecia em toda
                      // operação — abrir mesa, incluir item, pagar — e dava a
                      // sensação de que o PDV recarregava a cada toque. Bloquear
                      // a interface também era redundante: `_work` já ignora uma
                      // segunda chamada enquanto a primeira não termina.
                      if (busy)
                        const Positioned(
                          top: 0,
                          left: 0,
                          right: 0,
                          child: LinearProgressIndicator(minHeight: 3),
                        ),
                    ],
                  ),
                ),
                PdvShortcutBar(message: _operationalMessage),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
