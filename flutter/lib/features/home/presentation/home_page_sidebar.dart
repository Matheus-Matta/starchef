// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O painel de operação da barra lateral: caixa, sincronização e atalhos.
///
/// Separado do `build` (`_ShellSection`) por tamanho: era metade do arquivo.
mixin _SidebarSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;
  TerminalTopology get topology;
  NetworkSyncStatus get networkStatus;

  Map<String, dynamic>? get cashSession;
  Map<String, dynamic>? get pendingCashMovement;
  List<Map<String, dynamic>> get restaurants;
  String? get selectedRestaurantId;
  String get flowStep;
  set flowStep(String value);
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  String? get orderType;
  set orderType(String? value);
  bool get sidebarExpanded;
  set sidebarExpanded(bool value);
  bool get loading;
  String? get loadErrorMessage;
  bool get cashSessionFromCache;
  bool get hasCashDivergence;
  bool get offlineMode;
  bool get isSecondaryStation;
  bool get principalReachable;
  bool get _canSeeCashBalance;
  String get _cashBalanceLabel;
  int get offlinePendingCount;

  PdvUpdateStatus get versionStatus;
  PdvDestination get _selectedDestination;

  Future<void> _load();
  Future<void> _navigateTo(PdvDestination destination);
  String _sidebarUserSubtitle();
  Future<void> _checkPdvVersion();
  Future<void> _goHome();
  void _goBack();
  Future<void> _openCash();
  void _onCashMenuSelected(String value);
  List<PopupMenuEntry<String>> _cashMenuItems();
  Future<void> _showMovementApproval();
  Future<void> _toggleCashBalanceVisibility();
  Future<void> _openOutboxReview();
  Future<void> _openTopologySettings();
  Future<void> _changeRestaurant(String value);
  Future<void> _changeScaleRestaurant(String value);
  Widget _operationStat(String label, String value, IconData icon);

  Widget _sidebarOperationPanel({bool compact = false}) {
    final scheme = Theme.of(context).colorScheme;
    if (compact) {
      if (cashSession == null) {
        return IconButton.filled(
          tooltip: 'Abrir caixa',
          onPressed: _openCash,
          icon: const Icon(Icons.lock_open_outlined),
        );
      }
      return PopupMenuButton<String>(
        tooltip: 'Caixa aberto · $_cashBalanceLabel',
        onSelected: _onCashMenuSelected,
        itemBuilder: (_) => _cashMenuItems(),
        child: Container(
          width: AppTheme.controlHeight,
          height: AppTheme.controlHeight,
          decoration: BoxDecoration(
            color: scheme.primary,
            borderRadius: AppTheme.radius,
          ),
          child: const Icon(Icons.point_of_sale, color: Colors.white, size: 20),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (restaurants.isNotEmpty) ...[
          DropdownButtonFormField<String>(
            initialValue: selectedRestaurantId,
            isExpanded: true,
            decoration: const InputDecoration(
              labelText: 'Unidade',
              prefixIcon: Icon(Icons.storefront_outlined, size: 18),
            ),
            items: restaurants
                .map(
                  (item) => DropdownMenuItem(
                    value: '${item['id']}',
                    child: Text(
                      '${item['trade_name'] ?? item['name']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                )
                .toList(),
            onChanged: busy || restaurants.length == 1
                ? null
                : (value) {
                    if (value != null) _changeRestaurant(value);
                  },
          ),
          const SizedBox(height: 10),
        ],
        if (cashSession == null)
          ShadButton(
            onPressed: _openCash,
            height: AppTheme.controlHeight,
            leading: const Icon(Icons.lock_open_outlined, size: 18),
            child: const Text('Abrir caixa'),
          )
        else
          PopupMenuButton<String>(
            tooltip: 'Ações do caixa',
            onSelected: _onCashMenuSelected,
            itemBuilder: (_) => _cashMenuItems(),
            child: Container(
              padding: const EdgeInsets.fromLTRB(11, 9, 9, 9),
              decoration: BoxDecoration(
                color: scheme.surfaceContainer,
                borderRadius: AppTheme.radius,
                border: Border.all(color: scheme.outlineVariant),
              ),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: scheme.primary,
                      borderRadius: AppTheme.radius,
                    ),
                    child: const Icon(
                      Icons.point_of_sale,
                      color: Colors.white,
                      size: 17,
                    ),
                  ),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          cashSessionFromCache
                              ? 'CAIXA OFFLINE'
                              : 'CAIXA ABERTO',
                          style: TextStyle(
                            color: cashSessionFromCache
                                ? scheme.error
                                : scheme.primary,
                            fontSize: 9,
                            fontWeight: FontWeight.w900,
                            letterSpacing: .7,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          _cashBalanceLabel,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w900,
                            letterSpacing: .5,
                          ),
                        ),
                        Text(
                          '${cashSession!['station']}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: scheme.onSurfaceVariant,
                            fontSize: 9,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Icon(Icons.more_vert, size: 17),
                ],
              ),
            ),
          ),
      ],
    );
  }

  (String, String, IconData) get _workspaceIdentity {
    if (flowStep == 'scale-workstation') {
      return (
        'Estação de balança',
        'Pesagem rápida e leitura de comandas',
        Icons.scale_outlined,
      );
    }
    if (flowStep == 'orders') {
      return (
        'Pedidos',
        'Consulta, edição e pagamentos pendentes',
        Icons.receipt_long_outlined,
      );
    }
    if (flowStep == 'payment') {
      return (
        activeOrder == null
            ? 'Pagamento'
            : 'Pagamento · Pedido #${activeOrder!['sequence']}',
        'Conferência e finalização do pedido',
        Icons.payments_outlined,
      );
    }
    if (activeOrder != null) {
      return (
        'Pedido #${activeOrder!['sequence']}',
        'Cardápio e resumo do atendimento',
        Icons.shopping_bag_outlined,
      );
    }
    if (flowStep == 'context' || flowStep == 'table_details') {
      return (
        orderType == 'command' ? 'Comandas' : 'Mesas',
        'Selecione o contexto do atendimento',
        orderType == 'command'
            ? Icons.qr_code_2_outlined
            : Icons.table_restaurant_outlined,
      );
    }
    return (
      'Novo atendimento',
      'Escolha como o pedido será iniciado',
      Icons.grid_view_outlined,
    );
  }
}
