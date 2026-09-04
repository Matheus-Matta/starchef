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
  TerminalTopology get topology;
  PdvUpdateStatus get versionStatus;
  NetworkSyncStatus get networkStatus;

  Map<String, dynamic>? get activeOrder;
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get cashSession;
  List<Map<String, dynamic>> get restaurants;
  List<Map<String, dynamic>> get orderItems;
  String get flowStep;
  set flowStep(String value);
  String? get orderType;
  String? get selectedRestaurantId;
  bool get loading;
  bool get refreshing;
  bool get sidebarExpanded;
  set sidebarExpanded(bool value);
  bool get offlineMode;
  bool get isSecondaryStation;
  bool get principalReachable;
  bool get hasCashDivergence;
  bool get _canSeeCashBalance;
  String get _cashBalanceLabel;
  int get offlinePendingCount;

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
  Future<void> _openOutboxReview();
  Future<void> _openTopologySettings();
  Future<void> _openHelp();
  Future<void> _openCommand(Map<String, dynamic> command);
  Future<void> _changeScaleRestaurant(String value);
  bool get cashSessionFromCache;
  Map<String, dynamic>? get pendingCashMovement;
  Future<void> _showMovementApproval();
  String? get loadErrorMessage;
  List<Map<String, dynamic>> get products;
  Widget _sidebarOperationPanel({bool compact});
  (String, String, IconData) get _workspaceIdentity;
  Widget _startPanel();
  Widget _catalog();
  Widget _cart();
  Widget _ordersPage();
  Widget _paymentPage();
  Widget _tableContextPanel();
  Widget _commandContextPanel();

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

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final windowWidth = MediaQuery.sizeOf(context).width;
    final compactHeader = windowWidth < 1320;
    final sidebarIsExpanded = sidebarExpanded && windowWidth >= 1180;
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
          PdvSidebar(
            expanded: sidebarIsExpanded,
            selected: _selectedDestination,
            onToggle: () => setState(() => sidebarExpanded = !sidebarExpanded),
            onSelected: (destination) => unawaited(_navigateTo(destination)),
            userName: widget.controller.session!.user.name.trim().isEmpty
                ? widget.controller.session!.user.username
                : widget.controller.session!.user.name,
            userSubtitle: _sidebarUserSubtitle(),
            onLogout: widget.controller.logout,
            contextPanel: _sidebarOperationPanel(),
            compactContextPanel: _sidebarOperationPanel(compact: true),
            showOrders: widget.controller.session!.user.canViewOrders,
            showFinance: widget.controller.session!.user.canAccessCash,
            showScale:
                widget.controller.session!.user.canManageOrders ||
                widget.controller.session!.user.canProcessPayments,
            showSettings: true,
            versionStatus: versionStatus,
            onCheckVersion: () => unawaited(_checkPdvVersion()),
          ),
          Expanded(
            child: Scaffold(
              appBar: AppBar(
                toolbarHeight: 72,
                titleSpacing: 20,
                title: Row(
                  children: [
                    Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color: scheme.primaryContainer,
                        borderRadius: AppTheme.radius,
                        border: Border.all(color: scheme.outlineVariant),
                      ),
                      child: Icon(
                        _workspaceIdentity.$3,
                        size: 19,
                        color: scheme.primary,
                      ),
                    ),
                    const SizedBox(width: 11),
                    Expanded(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _workspaceIdentity.$1,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          if (!compactHeader)
                            Text(
                              _workspaceIdentity.$2,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: scheme.onSurfaceVariant,
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                actions: [
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      vertical: 10,
                      horizontal: 6,
                    ),
                    child: PdvConnectionBadge(
                      status: networkStatus,
                      // Clicar no badge abre a revisão da fila. Um item
                      // bloqueado não é resolvido por "sincronizar de novo":
                      // ele precisa ser inspecionado.
                      onPressed: offlinePendingCount > 0
                          ? () => unawaited(_openOutboxReview())
                          : null,
                    ),
                  ),
                  if (isSecondaryStation)
                    Padding(
                      padding: const EdgeInsets.symmetric(
                        vertical: 10,
                        horizontal: 2,
                      ),
                      child: PdvPrincipalBadge(
                        connected: principalReachable,
                        compact: compactHeader,
                        detail: topology.status.message,
                        onPressed: () => unawaited(_openTopologySettings()),
                      ),
                    ),
                  if (flowStep != 'type' || activeOrder != null)
                    IconButton(
                      tooltip: 'Voltar',
                      onPressed: _goBack,
                      icon: const Icon(Icons.arrow_back),
                    ),
                  IconButton(
                    tooltip: 'Ir para o início',
                    onPressed: _goHome,
                    icon: const Icon(Icons.home_outlined),
                  ),
                  // Ajuda ao lado do Home: é onde o operador procura quando
                  // não sabe o que uma tecla faz, e a lista que ela mostra sai
                  // do mesmo registro que o teclado consulta.
                  IconButton(
                    tooltip: 'Ajuda e atalhos (F1)',
                    onPressed: () => unawaited(_openHelp()),
                    icon: const Icon(Icons.help_outline),
                  ),
                  IconButton(
                    tooltip: widget.isDark
                        ? 'Usar tema claro'
                        : 'Usar tema escuro',
                    onPressed: widget.onToggleTheme,
                    icon: Icon(
                      widget.isDark
                          ? Icons.light_mode_outlined
                          : Icons.dark_mode_outlined,
                    ),
                  ),
                  IconButton(
                    tooltip: refreshing ? 'Atualizando...' : 'Atualizar',
                    onPressed: refreshing ? null : _load,
                    // Toda a sinalização de recarga cabe aqui: o operador vê
                    // que algo está acontecendo sem perder a tela em que está.
                    icon: refreshing
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.refresh),
                  ),
                  IconButton(
                    tooltip: 'Fechar aplicação',
                    onPressed: widget.onClose,
                    style: IconButton.styleFrom(foregroundColor: scheme.error),
                    icon: const Icon(Icons.power_settings_new),
                  ),
                  const SizedBox(width: 10),
                ],
                bottom: widget.controller.offlineMode
                    ? PreferredSize(
                        preferredSize: const Size.fromHeight(38),
                        child: Container(
                          width: double.infinity,
                          height: 38,
                          color: scheme.errorContainer,
                          alignment: Alignment.center,
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.cloud_off_outlined,
                                size: 18,
                                color: scheme.onErrorContainer,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                'Modo Offline — login validado no cache local; a Retaguarda está indisponível.',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: scheme.onErrorContainer,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ],
                          ),
                        ),
                      )
                    : null,
              ),
              body: Stack(
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
                  else if (flowStep == 'orders')
                    _ordersPage()
                  else if (activeOrder == null && flowStep == 'type')
                    _startPanel()
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
                    )
                  else if (flowStep == 'payment')
                    _paymentPage()
                  else
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final cartWidth = constraints.maxWidth < 980
                            ? 350.0
                            : constraints.maxWidth >= 1500
                            ? 420.0
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
                                  style: TextStyle(fontWeight: FontWeight.w800),
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
          ),
        ],
      ),
    );
  }
}
