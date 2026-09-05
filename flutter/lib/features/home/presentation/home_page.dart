// A tela guarda o estado e o ciclo de vida; cada assunto vive num `part` como
// um mixin. Membro definido aqui e consumido por uma seção através da
// declaração abstrata dela é marcado como `unused_element`: o analisador não
// liga as duas pontas entre mixins.
//
// O custo assumido: código realmente morto neste arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/errors/app_error.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/errors/app_error_host.dart';
import '../../../core/data/local_id.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/formatters/value_formatters.dart';
import '../../../core/storage/local_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/pdv_update_service.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../../core/widgets/app_dialog.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../../core/widgets/supervisor_close_dialog.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../devices/domain/local_print_renderer.dart';
import '../../devices/presentation/device_list_page.dart';
import '../../devices/presentation/print_queue_dialog.dart';
import '../../devices/presentation/printer_selection_dialog.dart';
import '../../devices/services/local_device_agent.dart';
import '../../orders/data/local_order_store.dart';
import '../../orders/presentation/order_presenter.dart';
import '../../orders/presentation/order_data_source.dart';
import '../../orders/presentation/order_cart_panel.dart';
import '../../orders/presentation/item_void_reason_dialog.dart';
import '../../orders/presentation/product_config_dialog.dart';
import '../../scale/presentation/scale_workstation_page.dart';
import '../../settings/presentation/terminal_preferences_dialog.dart';
import '../../sync/presentation/outbox_review_dialog.dart';
import '../../scale/services/scale_window_launcher.dart';
import '../../topology/data/local_topology_store.dart';
import '../../topology/domain/local_topology_config.dart';
import '../../topology/presentation/local_topology_dialog.dart';
import '../../topology/services/local_topology_service.dart';
import '../../topology/services/terminal_topology.dart';
import '../../../core/input/code_lookup_service.dart';
import '../../../core/input/pdv_input_router.dart';
import '../../../core/input/pdv_screen.dart';
import '../../../core/input/pdv_shortcuts.dart';
import 'pdv_help_dialog.dart';
import '../data/pdv_repository.dart';
import 'pdv_navigation_shell.dart';
import '../../cash/presentation/cash_auth_dialog.dart';
import 'pdv_cash_center_dialog.dart';
import 'pdv_presenter.dart';
import 'pdv_settings_menu_dialog.dart';
import 'pdv_shortcut_bar.dart';
import 'product_catalog_panel.dart';
import 'table_details_panel.dart';

part 'home_page_cash.dart';
part 'home_page_cash_ops.dart';
part 'home_page_commands.dart';
part 'home_page_commands_view.dart';
part 'home_page_customer.dart';
part 'home_page_kitchen.dart';
part 'home_page_order.dart';
part 'home_page_product.dart';
part 'home_page_orders.dart';
part 'home_page_orders_view.dart';
part 'home_page_payment.dart';
part 'home_page_payment_view.dart';
part 'home_page_receipt.dart';
part 'home_page_panels.dart';
part 'home_page_shared.dart';
part 'home_page_shell.dart';
part 'home_page_sidebar.dart';
part 'home_page_fiscal.dart';
part 'home_page_input.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.controller,
    required this.isDark,
    required this.onToggleTheme,
    required this.isFullScreen,
    required this.onToggleFullScreen,
    required this.onClose,
    required this.preferences,
  });

  final AuthController controller;
  final bool isDark;
  final VoidCallback onToggleTheme;
  final bool isFullScreen;
  final VoidCallback onToggleFullScreen;
  final VoidCallback onClose;
  final LocalPreferences preferences;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage>
    with
        _HomePageShared,
        _CashSection,
        _CashOpsSection,
        _CommandSection,
        _CommandView,
        _FiscalSection,
        _InputSection,
        _CustomerSection,
        _KitchenSection,
        _OrderSection,
        _ProductSection,
        _OrdersSection,
        _OrdersView,
        _PaymentSection,
        _PaymentView,
        _ReceiptSection,
        _ShellSection,
        _SidebarSection,
        _PanelsSection {
  @override
  ApiClient get api => widget.controller.repository.apiClient;
  @override
  String get token => widget.controller.session!.accessToken;
  @override
  String? get restaurantId => selectedRestaurantId;
  @override
  Map<String, dynamic>? get selectedRestaurant =>
      restaurants.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == restaurantId,
        orElse: () => null,
      );
  @override
  double get defaultServiceFeePercent =>
      _number(selectedRestaurant?['default_service_fee_percent']);

  @override
  bool loading = true;

  /// Recarga em segundo plano: os dados estão sendo atualizados, mas a tela
  /// atual continua utilizável.
  @override
  bool refreshing = false;
  @override
  bool busy = false;
  @override
  bool printingReceipt = false;
  @override
  bool emittingInvoice = false;
  @override
  bool divergenceDialogOpen = false;
  @override
  bool movementApprovalDialogOpen = false;
  @override
  String flowStep = 'type';
  @override
  String? orderType;
  @override
  String search = '';
  @override
  String? category;
  @override
  Map<String, dynamic>? cashSession;

  /// A sessão de caixa veio do cache local, não de uma leitura ao servidor.
  /// O estado pode ter mudado em outro terminal enquanto este esteve offline.
  @override
  bool cashSessionFromCache = false;

  /// Id da sessão para a qual o saldo foi liberado nesta tela (§conferência
  /// às cegas). Guardar o id, e não um `bool`, faz a liberação esquecer
  /// sozinha quando o turno muda — sem isso, o saldo revelado num fechamento
  /// continuaria visível no caixa seguinte, aberto por outra pessoa.
  String? _cashBalanceRevealedForSessionId;
  @override
  Map<String, dynamic>? activeOrder;
  @override
  Map<String, dynamic>? selectedTable;
  @override
  Map<String, dynamic>? selectedCommand;
  @override
  String commandSearch = '';
  @override
  Map<String, dynamic>? selectedCustomer;
  @override
  Map<String, dynamic>? pendingCashMovement;
  @override
  List<Map<String, dynamic>> stations = [];
  @override
  List<Map<String, dynamic>> restaurants = [];
  @override
  List<Map<String, dynamic>> products = [];
  @override
  List<Map<String, dynamic>> categories = [];
  @override
  List<Map<String, dynamic>> tables = [];
  @override
  List<Map<String, dynamic>> commands = [];
  @override
  List<Map<String, dynamic>> orderItems = [];

  /// Item sob o cursor do teclado, na lista do pedido.
  ///
  /// `+`, `-` e Delete agem sobre ELE. Guardar o id (e não o índice) é o que
  /// mantém a seleção no mesmo item depois de um recarregamento em que a
  /// ordem da lista mudou.
  @override
  String? selectedOrderItemId;
  @override
  List<Map<String, dynamic>> paymentMethods = [];
  @override
  List<Map<String, dynamic>> registeredPayments = [];
  @override
  List<Map<String, dynamic>> orders = [];
  @override
  bool ordersLoading = false;
  @override
  String? loadErrorMessage;
  @override
  String orderStatusFilter = 'pending';
  @override
  String orderSearch = '';
  @override
  String? orderTypeFilter;
  @override
  String orderOrdering = '-updated_at';
  @override
  DateTimeRange? orderDateRange;

  /// A busca não alcançou o servidor e o resultado saiu do que já estava
  /// guardado — pode faltar pedido antigo. A tela avisa em vez de fingir que
  /// achou tudo.
  @override
  bool ordersPartial = false;
  @override
  final ordersSearchController = TextEditingController();
  @override
  final ordersSearchFocus = FocusNode(debugLabel: 'orders-search');
  @override
  final commandSearchFocus = FocusNode(debugLabel: 'command-search');
  @override
  Timer? ordersSearchDebounce;
  @override
  String? selectedPaymentMethod;
  @override
  String paymentDigits = '0';
  @override
  String? removingPaymentId;
  @override
  final paymentReference = TextEditingController();
  @override
  final paymentAmount = TextEditingController();
  @override
  String? selectedRestaurantId;
  @override
  late final LocalDeviceAgent deviceAgent;
  PrinterAvailabilityPhase lastPrinterPhase = PrinterAvailabilityPhase.checking;
  late final PdvRepository repository;
  late final PdvPresenter presenter;
  late final PdvUpdateService updateService;
  @override
  PdvUpdateStatus versionStatus = const PdvUpdateStatus.checking();

  /// Porta de entrada da tela para os pedidos guardados no banco do Caixa
  /// Principal. Não é mais um banco à parte (ver [LocalOrderStore]).
  @override
  late final LocalOrderStore orderStore = LocalOrderStore(api: api);
  StreamSubscription<NetworkSyncStatus>? syncStatusSubscription;
  StreamSubscription<void>? ordersSignalSubscription;
  StreamSubscription<String>? realtimeSignalSubscription;
  Timer? realtimeRefreshDebounce;
  final Set<String> pendingRealtimeTopics = {};
  bool realtimeRefreshRunning = false;
  bool realtimeRefreshQueued = false;
  @override
  late final TerminalTopology topology;

  /// O controlador central de entrada: teclado, leitor USB, leitor serial e
  /// área de transferência entram por aqui e saem como o MESMO evento.
  @override
  late final PdvInputRouter inputRouter;
  @override
  CodeLookupService? codeLookup;
  StreamSubscription<ScannedCode>? codeSubscription;
  StreamSubscription<PdvShortcut>? shortcutSubscription;

  /// Enquanto o modal de configuração de produto está aberto, uma nova leitura
  /// do MESMO produto soma quantidade lá dentro em vez de abrir outro modal.
  @override
  StreamController<void>? productScanRepeats;
  @override
  String? scanningProductId;
  @override
  NetworkSyncStatus networkStatus = const NetworkSyncStatus(
    phase: NetworkSyncPhase.unknown,
  );
  @override
  bool offlineMode = false;

  /// Este terminal é um Caixa Cliente, que depende do principal para gravar.
  @override
  bool get isSecondaryStation => topology.isClient;

  /// O principal respondeu ao último teste de conexão.
  @override
  bool get principalReachable => topology.isClientReady;
  @override
  int offlinePendingCount = 0;

  /// Numerador dos recebimentos encenados, para dar um id local a cada linha.
  @override
  int stagedPaymentSequence = 0;

  /// O valor no teclado foi DIGITADO pelo operador?
  ///
  /// Enquanto for `false`, ele é apenas a sugestão "receba o restante" e
  /// acompanha o pedido. Assim que alguém digita, o valor é dele e nada mais
  /// o reescreve — receber R$ 20,00 de uma conta de R$ 12,43 é uma decisão.
  @override
  bool paymentAmountTyped = false;

  /// Conclusão em curso. Sem isto, um duplo clique em "Concluir pedido"
  /// percorria o gesto inteiro duas vezes — dois recibos e dois DANFEs.
  @override
  bool completingOrder = false;

  /// Notas cuja autorização já está sendo aguardada nesta tela. Dois
  /// vigias sobre a mesma nota mandariam o DANFE para a impressora duas vezes.
  @override
  final Set<String> watchedFiscalInvoices = {};
  @override
  bool sidebarExpanded = true;

  /// Última filtragem do catálogo, para não refazê-la a cada build.
  ///
  /// A tela de vendas se reconstrói a cada tecla e a cada mudança de estado, e
  /// o filtro varria o catálogo INTEIRO em todas elas — normalizando o termo
  /// de busca uma vez por produto, ainda por cima. A lista de produtos só é
  /// reatribuída no carregamento (nunca alterada no lugar), então identidade
  /// da lista + categoria + termo descrevem o resultado por inteiro.
  ///
  /// O resultado é o mesmo de antes; muda só quantas vezes ele é calculado.
  List<Map<String, dynamic>>? _visibleCache;
  List<Map<String, dynamic>>? _visibleSource;
  String? _visibleCategory;
  String _visibleTerm = '';

  @override
  List<Map<String, dynamic>> get visibleProducts {
    final term = search.trim().toLowerCase();
    final cached = _visibleCache;
    if (cached != null &&
        identical(products, _visibleSource) &&
        category == _visibleCategory &&
        term == _visibleTerm) {
      return cached;
    }
    final filtered = products.where((product) {
      final matchesCategory =
          category == null || '${product['category']}' == category;
      return matchesCategory &&
          (term.isEmpty ||
              '${product['name']}'.toLowerCase().contains(term) ||
              '${product['internal_code'] ?? ''}'.toLowerCase().contains(
                term,
              ) ||
              '${product['category_name'] ?? ''}'.toLowerCase().contains(term));
    }).toList();
    _visibleSource = products;
    _visibleCategory = category;
    _visibleTerm = term;
    return _visibleCache = filtered;
  }

  @override
  double get paidTotal => registeredPayments.fold(
    0,
    (total, payment) => total + _number(payment['amount']),
  );
  @override
  double get remainingTotal =>
      (_number(activeOrder?['total']) - paidTotal).clamp(0, double.infinity);
  @override
  double get changeTotal => registeredPayments.fold(
    0,
    (total, payment) => total + _number(payment['change_amount']),
  );
  @override
  double get receivedTotal => registeredPayments.fold(
    0,
    (total, payment) =>
        total + _number(payment['amount']) + _number(payment['change_amount']),
  );
  @override
  double get paymentValue => (int.tryParse(paymentDigits) ?? 0) / 100;
  @override
  Map<String, dynamic>? get selectedMethod =>
      paymentMethods.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == selectedPaymentMethod,
        orElse: () => null,
      );
  @override
  bool get selectedMethodIsCash => selectedMethod?['method_type'] == 'cash';
  @override
  double get pendingChange =>
      selectedMethodIsCash && paymentValue > remainingTotal
      ? paymentValue - remainingTotal
      : 0;
  @override
  bool get hasCashDivergence =>
      cashSession?['status'] == 'pending_manager_approval';
  @override
  double get cashBalance {
    if (cashSession?['current_balance'] != null) {
      return _number(cashSession!['current_balance']);
    }
    return (cashSession?['movements'] as List? ?? const [])
        .cast<Map<String, dynamic>>()
        .where((movement) => movement['status'] == 'approved')
        .fold(0, (total, movement) => total + _number(movement['amount']));
  }

  /// O operador pode ver o número de `cashBalance` agora?
  ///
  /// Por padrão não: o caixa faz a conferência às cegas, sem saber quanto o
  /// sistema espera encontrar. Só quem administra a conta vê livremente
  /// ([AuthUser.canViewCashBalanceFreely]); qualquer outro perfil — inclusive
  /// gerente — precisa da senha de ações do caixa, verificada localmente e
  /// sem depender de rede (ver [_toggleCashBalanceVisibility]).
  @override
  bool get _canSeeCashBalance =>
      widget.controller.session?.user.canViewCashBalanceFreely == true ||
      (_cashBalanceRevealedForSessionId != null &&
          _cashBalanceRevealedForSessionId == '${cashSession?['id'] ?? ''}');

  @override
  String get _cashBalanceLabel =>
      _canSeeCashBalance ? _money(cashBalance) : '••••••';

  /// Alterna a visibilidade do saldo no sidebar e no Financeiro do caixa.
  ///
  /// Esconder é imediato. Revelar exige senha — a mesma "senha de ações do
  /// caixa" já usada para autorizar sangria e divergência, conferida OFFLINE
  /// contra o hash sincronizado neste terminal — a menos que o próprio login
  /// já seja de administrador/proprietário.
  @override
  Future<void> _toggleCashBalanceVisibility() async {
    final sessionId = '${cashSession?['id'] ?? ''}';
    if (_canSeeCashBalance) {
      // Um admin que "esconde" o próprio acesso livre não trava nada — ele
      // continua vendo no próximo tap. Isso é intencional: a única coisa que
      // este botão sempre garante é apagar o que uma senha alheia liberou.
      setState(() => _cashBalanceRevealedForSessionId = null);
      return;
    }
    if (sessionId.isEmpty) return;
    final cashAuth = widget.controller.repository.cashAuth;
    final restaurant = restaurantId;
    if (cashAuth == null || restaurant == null) return;
    final authorized = await showCashAuthDialog(
      context,
      cashAuth: cashAuth,
      restaurantId: restaurant,
      title: 'Ver saldo do caixa',
      message:
          'Informe a senha de ações do caixa para ver o valor em dinheiro. '
          'A conferência deve ser feita às cegas — só libere se for '
          'realmente necessário.',
    );
    if (authorized && mounted) {
      setState(() => _cashBalanceRevealedForSessionId = sessionId);
    }
  }

  @override
  void initState() {
    super.initState();
    deviceAgent = LocalDeviceAgent(api: api, preferences: widget.preferences);
    deviceAgent.printerAvailability.addListener(_onPrinterStatusChanged);
    topology = TerminalTopology(
      api: api,
      deviceAgent: deviceAgent,
      preferences: widget.preferences,
      readIdentity: () {
        final user = widget.controller.session?.user;
        return TopologyIdentity(
          accessToken: widget.controller.session?.accessToken ?? '',
          // Num Caixa Secundário, estas credenciais viajam com cada operação
          // encaminhada: é com ELAS que o Caixa Principal entrega ao backend,
          // para a venda e a sessão de caixa nascerem no nome de quem
          // realmente atendeu.
          refreshToken: widget.controller.session?.refreshToken ?? '',
          accountId: user?.accountId ?? '',
          actorId: user?.id ?? '',
          actorName: user?.name ?? user?.username ?? '',
          terminalName: _terminalName,
          // A unidade escolhida quando já houver bootstrap; antes dele, a do
          // vínculo do usuário. Nenhuma das duas depende da nuvem agora.
          restaurantId: selectedRestaurantId ?? user?.restaurantId ?? '',
        );
      },
      // A chave de pareamento tem a mesma exigência do login: perder ela ao
      // fechar o PDV desconecta todos os caixas secundários. Guarda nas mesmas
      // camadas duráveis, incluindo o banco operacional.
      createStore: () => LocalTopologyStore(
        secretStorage: SecureTopologySecretStorage(
          valueStore: widget.controller.repository.credentials,
        ),
      ),
    );
    topology.addListener(_onTopologyChanged);
    inputRouter = PdvInputRouter(readContext: _readInputContext);
    codeSubscription = inputRouter.codes.listen(_onCodeScanned);
    shortcutSubscription = inputRouter.shortcuts.listen(_onShortcut);
    HardwareKeyboard.instance.addHandler(inputRouter.handleKeyEvent);
    repository = PdvRepository(api: api, accessToken: token);
    presenter = PdvPresenter(repository);
    updateService = PdvUpdateService();
    unawaited(_checkPdvVersion());
    networkStatus = api.syncStatus;
    syncStatusSubscription = api.syncStatusChanges.listen((status) {
      if (!mounted) return;
      final online = status.hasConnection;
      // A rede voltar é motivo para reler os dados, não para reconstruir a
      // tela. Como `_load` só apaga a tela na primeira carga, uma oscilação
      // agora passa despercebida pelo operador — antes ela devolvia o PDV a
      // uma tela em branco no meio do atendimento.
      final shouldRefresh =
          online &&
          !loading &&
          !refreshing &&
          (offlineMode || (offlinePendingCount > 0 && status.total == 0));
      setState(() {
        networkStatus = status;
        offlineMode = !online;
        offlinePendingCount = status.total;
      });
      if (online) widget.controller.markOnline();
      // Com a conexão de volta, o aviso de "sem conexão" perdeu o assunto e
      // sai sozinho — o operador não precisa fechá-lo à mão.
      if (online) ErrorCenterScope.read(context).dismissByKey('connectivity');
      if (shouldRefresh) unawaited(_load());
    });
    // Quando um pedido muda — porque chegou do servidor, do Caixa Principal ou
    // de uma edição offline —, a tela relê do armazenamento local. A leitura é
    // barata e local, então isso nunca prende a interface esperando a rede.
    ordersSignalSubscription = api.signals.on('orders').listen((_) {
      if (mounted) unawaited(_refreshFromSignal());
    });
    realtimeSignalSubscription = api.signals.changes
        .where((topic) => topic.startsWith('realtime:'))
        .listen(_scheduleRealtimeRefresh);
    _load();
  }

  @override
  Future<void> _checkPdvVersion() async {
    if (mounted) {
      setState(
        () => versionStatus = PdvUpdateStatus.checking(
          installed: versionStatus.installed,
        ),
      );
    }
    final result = await updateService.check(
      onInstalled: (installed) {
        if (!mounted) return;
        setState(
          () => versionStatus = PdvUpdateStatus.checking(installed: installed),
        );
      },
    );
    if (mounted) setState(() => versionStatus = result);
  }

  void _scheduleRealtimeRefresh(String signal) {
    if (!mounted) return;
    pendingRealtimeTopics.add(signal.substring('realtime:'.length));
    realtimeRefreshDebounce?.cancel();
    realtimeRefreshDebounce = Timer(
      const Duration(milliseconds: 180),
      () => unawaited(_applyRealtimeRefresh()),
    );
  }

  Future<void> _applyRealtimeRefresh() async {
    if (!mounted) return;
    if (realtimeRefreshRunning) {
      realtimeRefreshQueued = true;
      return;
    }
    realtimeRefreshRunning = true;
    try {
      do {
        realtimeRefreshQueued = false;
        final topics = Set<String>.from(pendingRealtimeTopics);
        pendingRealtimeTopics.clear();
        final reloadCatalog = topics.any(
          const {
            'tables',
            'menu',
            'payments',
            'cash',
            'session',
            'pdv',
          }.contains,
        );
        if (reloadCatalog) await _load();

        if (topics.contains('customers') && restaurantId != null) {
          await api.get(
            '/customers/',
            query: {
              'restaurant': restaurantId,
              'is_active': true,
              'page_size': 200,
            },
            accessToken: token,
          );
        }

        if (topics.contains('devices') && restaurantId != null) {
          final query = {
            'restaurant': restaurantId,
            'is_active': true,
            'page_size': 100,
          };
          await Future.wait([
            api.get('/printers/', query: query, accessToken: token),
            api.get('/scales/', query: query, accessToken: token),
          ]);
        }

        if (topics.contains('orders')) {
          if (flowStep == 'orders') {
            await _reloadOrders();
          } else if (activeOrder != null) {
            await _refreshOrder();
          } else {
            await _warmOrdersCache();
          }
        }
      } while (realtimeRefreshQueued || pendingRealtimeTopics.isNotEmpty);
    } catch (error) {
      // O WebSocket é aceleração, não um novo ponto de falha: cache,
      // reconexão e o próximo evento tentam reconciliar novamente.
      if (mounted && error is ApiException && !error.isConnectivity) {
        _error(
          error,
          title: 'Não foi possível aplicar a atualização em tempo real',
        );
      }
    } finally {
      realtimeRefreshRunning = false;
    }
  }

  void _onPrinterStatusChanged() {
    final status = deviceAgent.printerAvailability.value;
    final disconnectedAfterUse =
        status.phase == PrinterAvailabilityPhase.unavailable &&
        lastPrinterPhase == PrinterAvailabilityPhase.available;
    lastPrinterPhase = status.phase;
    if (!mounted || !disconnectedAfterUse) return;
    // O aviso carrega a causa vinda do agente (qual impressora e por quê): o
    // texto genérico anterior mandava conferir cabo e porta mesmo quando o
    // problema era outro — impressora do sistema com nome errado, por
    // exemplo — e não dizia qual das impressoras do terminal falhou.
    showAppToast(
      context,
      '${status.message} O PDV continua disponível.',
      title: 'Impressora desconectada',
      severity: AppErrorSeverity.warning,
    );
  }

  /// Relê o que está na tela a partir da cópia local.
  Future<void> _refreshFromSignal() async {
    final scope = api.sessionScope;
    if (scope == null) return;
    await _reconcileLocalIds(scope);
    if (flowStep == 'orders') {
      final local = await _ordersFromStore(scope);
      if (!mounted || local.isEmpty) return;
      setState(() => orders = local);
      return;
    }
    final current = activeOrder;
    if (current == null || flowStep != 'order') return;
    final stored = await orderStore.read('${current['id']}', scope: scope);
    if (!mounted || stored == null) return;
    setState(() {
      activeOrder = stored;
      orderItems = (stored['items'] as List? ?? const [])
          .cast<Map<String, dynamic>>()
          .where((item) => item['status'] != 'voided')
          .toList();
    });
  }

  @override
  Future<List<Map<String, dynamic>>> _list(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    return repository.list(path, query: query);
  }

  /// Liga a rede local deste terminal.
  ///
  /// Chamada ANTES do bootstrap de dados e de novo depois dele. A ordem é o
  /// ponto: num Caixa Secundário é o Caixa Principal quem serve restaurantes e
  /// cardápio, então ligar o relay só depois da carga era pedir ao secundário
  /// que carregasse pela nuvem justamente o que ele deveria ler do principal —
  /// e, sem nuvem, ele nunca chegava a se conectar a ninguém.
  Future<void> _ensureTopology({String? restaurantId}) =>
      topology.ensure(restaurantId: restaurantId);

  void _onTopologyChanged() {
    if (!mounted) return;
    // O `nodeId` da topologia é a identidade da INSTALAÇÃO — o mesmo UUID que
    // já identifica este terminal no relay da rede local. Reusá-lo evita
    // inventar um segundo identificador para o caixa, e dispensa MAC, IP ou
    // nome do computador (nenhum estável, nenhum necessário).
    api.localStore?.installationId = topology.config?.nodeId;
    api.localStore?.terminalLabel = _terminalName;
    setState(() {});
  }

  /// Por que este terminal não pode usar o caixa aberto (409/403 do servidor).
  ///
  /// Guardado em vez de descartado porque a mensagem já diz quem está com o
  /// caixa, de onde e desde quando — é o que o operador precisa para decidir
  /// entre esperar e pedir uma transferência gerencial.
  String? cashSessionBlockMessage;

  /// UUID da instalação deste terminal, ou vazio antes de a topologia subir.
  String get _terminalInstallationId => topology.config?.nodeId ?? '';

  /// Nome amigável do terminal. Um padrão pelo papel até a loja renomeá-lo
  /// (Configurações › Terminais, no backoffice) — melhor do que expor o UUID
  /// cru numa mensagem de bloqueio.
  String get _terminalName {
    final nodeId = _terminalInstallationId;
    if (nodeId.isEmpty) return '';
    final suffix = nodeId.length <= 6 ? nodeId : nodeId.substring(0, 6);
    return isSecondaryStation
        ? 'Caixa Secundário $suffix'
        : 'Caixa Principal $suffix';
  }

  /// Campos de identidade enviados em toda operação de caixa.
  ///
  /// Sem eles o servidor não consegue cumprir "a sessão pertence ao usuário
  /// que abriu E ao terminal onde foi aberta": o backend já tinha o campo, mas
  /// este aplicativo nunca o preenchia.
  @override
  Map<String, dynamic> get _terminalIdentity {
    final nodeId = _terminalInstallationId;
    if (nodeId.isEmpty) return const {};
    return {
      'terminal_installation_id': nodeId,
      'terminal_name': _terminalName,
      'terminal_type': 'desktop',
      'terminal_role': isSecondaryStation ? 'secondary' : 'principal',
      // Mantido para servidores que ainda leem o campo antigo.
      'device_identifier': nodeId,
    };
  }

  /// Recarrega os dados do PDV.
  ///
  /// A tela só é apagada na primeira vez, quando ainda não há nada para
  /// mostrar. Depois disso a recarga acontece por baixo: os dados são
  /// trocados quando chegam e o operador continua na mesma tela, com o mesmo
  /// pedido aberto. Antes, qualquer oscilação de rede — cair e voltar —
  /// devolvia o PDV a uma tela em branco no meio do atendimento.
  @override
  Future<void> _load() async {
    final firstLoad = restaurants.isEmpty;
    setState(() {
      loading = firstLoad;
      refreshing = !firstLoad;
      loadErrorMessage = null;
    });
    try {
      // Primeiro o papel do terminal, só depois os dados. Num Caixa
      // Secundário é o principal quem responde `/restaurants/` e o cardápio;
      // ligar o relay depois da carga deixava o secundário tentando a nuvem
      // para sempre — e sem nuvem, sem PDV.
      try {
        await _ensureTopology();
      } catch (error) {
        if (mounted) {
          showAppToast(
            context,
            'A rede local não iniciou: $error',
            title: 'Rede local indisponível',
            severity: AppErrorSeverity.warning,
          );
        }
      }
      final bootstrap = await presenter.load(
        selectedRestaurantId: selectedRestaurantId,
        userRestaurantId: widget.controller.session!.user.restaurantId,
        userId: widget.controller.session!.user.id,
      );
      restaurants = bootstrap.restaurants;
      selectedRestaurantId = bootstrap.selectedRestaurantId;
      widget.controller.setActiveRestaurant(selectedRestaurantId);
      // O banco local precisa saber de qual unidade são os dados que ele
      // sincroniza, e o fechamento offline precisa da taxa de serviço
      // cadastrada — sem isso o total calculado aqui não bateria com o do
      // servidor quando a operação subisse.
      api.localStore
        ?..bindRestaurant(selectedRestaurantId)
        ..serviceFeePercent = defaultServiceFeePercent;
      await widget.controller.repository.cashAuth?.trySync(
        widget.controller.session!,
        restaurantId: selectedRestaurantId,
      );
      final catalog = bootstrap.catalog;
      stations = catalog.cashStations;
      products = catalog.products;
      categories = catalog.categories;
      tables = catalog.tables;
      commands = catalog.commands;
      paymentMethods = catalog.paymentMethods;
      // Agora com a unidade resolvida: é ela que assina as requisições ao
      // principal e que o agente de impressão consulta.
      await _ensureTopology(restaurantId: selectedRestaurantId);
      try {
        final currentSession = await api.get(
          '/cash-register/current/',
          query: {
            if (selectedRestaurantId != null)
              'restaurant': selectedRestaurantId,
          },
          accessToken: token,
        );
        // A sessão aberta no servidor é a fonte de verdade. Descartá-la por
        // divergência momentânea do catálogo deixava a tela pedindo abertura,
        // mas a API recusava porque o caixa já estava aberto.
        cashSession = currentSession;
        final movements = (cashSession?['movements'] as List? ?? const [])
            .cast<Map<String, dynamic>>();
        pendingCashMovement = movements
            .cast<Map<String, dynamic>?>()
            .firstWhere(
              (item) =>
                  item?['status'] == 'pending' &&
                  {
                    'withdrawal',
                    'supply',
                  }.contains('${item?['movement_type']}'),
              orElse: () => null,
            );
        // A leitura agora vem sempre do banco local (§3); o que interessa
        // avisar é quando ela não pôde ser confirmada com o servidor.
        cashSessionFromCache =
            currentSession['_local_first'] == true &&
            !api.syncStatus.hasConnection;
      } on ApiException catch (error) {
        // 404 significa "nenhum caixa aberto". Sem rede e sem cache prévio o
        // terminal também não sabe o estado do caixa; em ambos os casos ele
        // segue carregando, porque abrir/fechar já exige servidor e falharia
        // com mensagem própria.
        //
        // 409/403 são a resposta nova: o caixa está com outra pessoa, ou com
        // este operador em outra máquina. Não é falha de carga — é informação
        // que o operador precisa ler, e a tela continua utilizável para o
        // resto do atendimento.
        const blocked = {403, 409};
        if (error.statusCode != null &&
            error.statusCode != 404 &&
            !blocked.contains(error.statusCode)) {
          rethrow;
        }
        cashSessionBlockMessage = blocked.contains(error.statusCode)
            ? error.message
            : null;
        cashSession = null;
        pendingCashMovement = null;
        cashSessionFromCache = false;
        if (cashSessionBlockMessage != null && mounted) {
          showAppToast(
            context,
            cashSessionBlockMessage!,
            title: 'Caixa indisponível neste terminal',
            severity: AppErrorSeverity.warning,
          );
        }
      }
    } catch (error) {
      // Numa recarga de fundo o operador já tem uma tela utilizável: falhar
      // aqui não pode substituí-la por um erro de tela cheia. O alerta global
      // e o indicador de conexão já contam o que houve.
      if (firstLoad) {
        loadErrorMessage = error is ApiException
            ? error.message
            : 'Não foi possível carregar os dados iniciais do PDV.';
      }
      if (mounted && !(error is ApiException && error.isConnectivity)) {
        _error(error);
      }
    } finally {
      if (mounted) {
        setState(() {
          loading = false;
          refreshing = false;
        });
        // Guarda os pedidos recentes assim que o PDV abre, para que uma queda
        // de rede depois não impeça de reabrir um pedido lançado em outro
        // caixa. Fora do caminho crítico: o operador não espera por isso.
        unawaited(_warmOrdersCache());
        // Carga completa do catálogo operacional em segundo plano (§24): a
        // tela já está utilizável e não espera por ela.
        final restaurantForSync = restaurantId;
        if (restaurantForSync != null) {
          unawaited(api.syncService?.pullAll(restaurantId: restaurantForSync));
        }
        if (hasCashDivergence) {
          WidgetsBinding.instance.addPostFrameCallback(
            (_) => _showCashDivergence(),
          );
        } else if (pendingCashMovement != null) {
          WidgetsBinding.instance.addPostFrameCallback(
            (_) => _showMovementApproval(),
          );
        }
      }
    }
  }

  @override
  Future<void> _changeRestaurant(String value) async {
    if (value == selectedRestaurantId) return;
    setState(() {
      selectedRestaurantId = value;
      activeOrder = null;
      selectedTable = null;
      selectedCommand = null;
      selectedCustomer = null;
      orderItems = [];
      selectedOrderItemId = null;
      registeredPayments = [];
      paymentMethods = [];
      orderType = null;
      category = null;
      flowStep = 'type';
      // Aqui o conteúdo antigo precisa sair: manter o cardápio e as mesas do
      // restaurante anterior na tela levaria alguém a lançar no lugar errado.
      // É a única troca que ainda mostra "carregando".
      products = [];
      categories = [];
      tables = [];
      restaurants = [];
    });
    await _load();
  }

  @override
  Future<void> _changeScaleRestaurant(String value) async {
    await _changeRestaurant(value);
    if (mounted) setState(() => flowStep = 'scale-workstation');
  }

  Future<void> _openScaleWindow() async {
    try {
      await widget.controller.repository.sessionStore.save(
        widget.controller.session!,
      );
      final opened = await ScaleWindowLauncher.open(
        restaurantId: restaurantId,
        session: widget.controller.session!,
      );
      if (!mounted) return;
      if (opened) return;
    } catch (_) {
      // O fallback embutido mantém a operação disponível em plataformas sem
      // suporte a processos desktop ou quando o cofre local está indisponível.
    }
    if (mounted) setState(() => flowStep = 'scale-workstation');
  }

  /// Abre a revisão da fila e reflete o resultado no badge ao fechar.
  @override
  Future<void> _openOutboxReview() async {
    await OutboxReviewDialog.show(context, api);
    final pending = await api.pendingOperations();
    if (!mounted) return;
    setState(() => offlinePendingCount = pending);
  }

  void _openDeviceSettings(DeviceKind kind) {
    final id = restaurantId;
    if (id == null) return;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => DeviceListPage(
          kind: kind,
          api: api,
          token: token,
          restaurantId: id,
          preferences: widget.preferences,
        ),
      ),
    );
  }

  @override
  PdvDestination get _selectedDestination {
    if (flowStep == 'scale-workstation') return PdvDestination.scale;
    if (flowStep == 'orders') return PdvDestination.orders;
    if (flowStep == 'table_details' ||
        (flowStep == 'context' && orderType != 'command')) {
      return PdvDestination.tables;
    }
    return PdvDestination.menu;
  }

  @override
  Future<void> _navigateTo(PdvDestination destination) async {
    switch (destination) {
      case PdvDestination.menu:
        if (activeOrder != null) {
          setState(() => flowStep = 'order');
        } else {
          await _goHome();
        }
        return;
      case PdvDestination.tables:
        setState(() {
          activeOrder = null;
          selectedTable = null;
          selectedCommand = null;
          selectedCustomer = null;
          orderItems = [];
          registeredPayments = [];
          orderType = 'table_view';
          flowStep = 'context';
        });
        return;
      case PdvDestination.orders:
        await _openOrders();
        return;
      case PdvDestination.finance:
        if (!widget.controller.session!.user.canAccessCash) return;
        await _openCashCenter();
        return;
      case PdvDestination.scale:
        await _openScaleWindow();
        return;
      case PdvDestination.settings:
        await _openSettingsCenter();
        return;
    }
  }

  @override
  Future<void> _openCashCenter() async {
    final action = await PdvCashCenterDialog.show(
      context,
      cashSession: cashSession,
      balanceLabel: _cashBalanceLabel,
    );
    if (!mounted || action == null) return;
    if (action == 'open') await _openCash();
    if (action == 'supply' || action == 'withdrawal') {
      await _cashMovement(action);
    }
    if (action == 'close') await _closeCash();
  }

  Future<void> _openSettingsCenter() async {
    final scope = deviceAgent.printScope;
    final printQueue = scope == null
        ? null
        : await deviceAgent.printQueue?.summary(scope: scope);
    if (!mounted) return;
    final selection = await PdvSettingsMenuDialog.show(
      context,
      canManageDevices: widget.controller.session!.user.canManageDevices,
      topologyStatus: topology.config == null
          ? 'Entre novamente para habilitar a identidade deste caixa.'
          : topology.status.message,
      offlinePendingCount: offlinePendingCount,
      printQueueCount: printQueue?.total ?? 0,
      isDark: widget.isDark,
      isFullScreen: widget.isFullScreen,
    );
    if (!mounted || selection == null) return;
    if (selection == 'printer') _openDeviceSettings(DeviceKind.printer);
    if (selection == 'scale') _openDeviceSettings(DeviceKind.scale);
    if (selection == 'topology') await _openTopologySettings();
    if (selection == 'preferences' && mounted) {
      List<Map<String, dynamic>> printersForPreferences = const [];
      try {
        printersForPreferences = await _list(
          '/printers/',
          query: {
            'restaurant': restaurantId,
            'is_active': true,
            'page_size': 100,
          },
        );
      } catch (_) {
        // Sem impressoras carregadas, o diálogo só perde a lista da master —
        // as demais preferências continuam editáveis normalmente.
      }
      if (mounted) {
        await TerminalPreferencesDialog.show(
          context,
          widget.preferences,
          printers: printersForPreferences,
        );
      }
    }
    if (selection == 'print_queue' && mounted) {
      await PrintQueueDialog.show(context, deviceAgent);
    }
    if (selection == 'outbox' && mounted) await _openOutboxReview();
    if (selection == 'theme') widget.onToggleTheme();
    if (selection == 'fullscreen') widget.onToggleFullScreen();
  }

  @override
  Future<void> _openTopologySettings() async {
    // O diálogo pode ser aberto antes de a carga terminar: garantir a rede
    // local aqui é o que permite corrigir o endereço do principal justamente
    // quando ele está errado — que é quando os dados não carregam.
    await _ensureTopology();
    if (!mounted) return;
    final service = topology;
    final current = service.config;
    if (current == null) {
      showAppToast(
        context,
        'A sessão restaurada não contém a identidade da conta. '
        'Saia e entre novamente antes de configurar a rede local.',
        title: 'Sessão incompleta',
        severity: AppErrorSeverity.warning,
      );
      return;
    }
    final candidate = await showLocalTopologyDialog(
      context: context,
      config: current,
      status: service.status,
      canEdit: widget.controller.session!.user.canManageTopology,
    );
    if (!mounted || candidate == null) return;
    setState(() => busy = true);
    try {
      await service.reconfigure(candidate);
      if (!mounted) return;
      final degraded =
          candidate.mode == LocalTopologyMode.client && !service.status.ready;
      // Sem este aviso, uma chave vazia ou a caixa de rede confiável
      // desmarcada faziam o Caixa Principal salvar "com sucesso" e só nunca
      // abrir a porta — o operador só descobria reabrindo o diálogo e lendo
      // o texto pequeno do status, o que parecia "QR Code parou de
      // funcionar" sem nenhum erro visível.
      final principalLocalOnly =
          candidate.mode == LocalTopologyMode.principal &&
          service.status.phase == LocalTopologyPhase.principalLocalOnly;
      if (degraded) {
        showAppToast(
          context,
          'Modo Cliente salvo, mas o Caixa Principal está indisponível.',
          title: 'Rede local',
          severity: AppErrorSeverity.warning,
        );
      } else if (principalLocalOnly) {
        showAppToast(
          context,
          service.status.message,
          title: 'Rede local não foi ligada',
          severity: AppErrorSeverity.warning,
        );
      }
    } catch (error) {
      if (mounted) _error(error);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  /// Volta à tela inicial do atendimento.
  ///
  /// A volta é imediata: o cardápio e as mesas já estão em memória e mudam
  /// pouco. A atualização segue por baixo, sem prender o operador entre um
  /// pedido e o próximo.
  /// O pedido aberto nao tem nada dentro?
  ///
  /// Item cancelado nao conta: uma comanda em que tudo foi cancelado continua
  /// sem conteudo, e prende a mesa do mesmo jeito.
  bool get _activeOrderIsEmpty {
    if (activeOrder == null) return false;
    if (const {
      'paid',
      'cancelled',
      'refunded',
    }.contains('${activeOrder?['status']}')) {
      return false;
    }
    final hasItems = orderItems.any(
      (item) => !const {
        'cancelled',
        'comped',
        'voided',
      }.contains('${item['status'] ?? ''}'),
    );
    return !hasItems && registeredPayments.isEmpty;
  }

  /// Descarta o pedido que foi aberto e não virou nada.
  ///
  /// Abrir uma comanda cria o pedido na hora — é ele que ocupa a comanda. Se o
  /// operador sai sem lançar item nenhum, esse pedido vazio fica no sistema
  /// segurando a comanda, e o próximo cliente que pegar a mesma não consegue
  /// usá-la. Não é um cancelamento comercial (não há consumo a estornar nem
  /// motivo a registrar), então não pede senha nem justificativa.
  ///
  /// É melhor-esforço de propósito: se o descarte não subir, a venda vazia é o
  /// menor dos problemas e nada disso pode atrapalhar o operador que só quis
  /// voltar para a tela inicial.
  Future<void> _discardEmptyOrder(Map<String, dynamic> order) async {
    try {
      await api.post(
        '/orders/${order['id']}/cancel/',
        body: const {},
        accessToken: token,
      );
      AppLogger.instance.info(
        'pedido_vazio_descartado',
        data: {'pedido': '${order['id']}', 'comanda': selectedCommand?['code']},
      );
    } catch (error) {
      // Um pedido que nunca subiu é descartado aqui mesmo, sem rede (o
      // gateway reconhece o id temporário). Sobra o caso do pedido que o
      // servidor já conhece e o terminal está offline: aí a comanda continua
      // ocupada até alguém cancelá-lo pela tela de Pedidos — chato, mas não
      // impede nada do que o operador está fazendo agora.
      AppLogger.instance.warning(
        'pedido_vazio_nao_descartado',
        data: {'pedido': '${order['id']}', 'causa': '$error'},
      );
    }
  }

  @override
  Future<void> _goHome() async {
    // O pedido é capturado ANTES do `setState` (depois dele não há mais o que
    // descartar) e o descarte segue em segundo plano: voltar para o início é
    // um gesto de navegação e não pode esperar a rede — sem conexão, a espera
    // seria o tempo inteiro do timeout com a tela parada.
    final discardable = _activeOrderIsEmpty ? activeOrder : null;
    if (discardable != null) unawaited(_discardEmptyOrder(discardable));
    setState(() {
      activeOrder = null;
      selectedTable = null;
      selectedCommand = null;
      selectedCustomer = null;
      orderItems = [];
      registeredPayments = [];
      orderType = null;
      flowStep = 'type';
    });
    unawaited(_load());
  }

  @override
  void _goBack() {
    if (flowStep == 'payment' && activeOrder != null) {
      // Recebimento montado não existe fora desta tela: voltar o descarta. O
      // operador precisa saber disso ANTES, senão sairia achando que o
      // pagamento ficou guardado em algum lugar.
      if (stagedPayments.isNotEmpty) {
        unawaited(_confirmLeavingPayment());
        return;
      }
      setState(() => flowStep = 'order');
    } else if (flowStep == 'table_details') {
      setState(() => flowStep = 'context');
    } else if (flowStep == 'context') {
      setState(() => flowStep = 'type');
    } else if (activeOrder != null) {
      _goHome();
    }
  }

  @override
  void dispose() {
    deviceAgent.printerAvailability.removeListener(_onPrinterStatusChanged);
    deviceAgent.dispose();
    unawaited(orderStore.close());
    ordersSignalSubscription?.cancel();
    realtimeSignalSubscription?.cancel();
    realtimeRefreshDebounce?.cancel();
    pendingRealtimeTopics.clear();
    syncStatusSubscription?.cancel();
    topology.removeListener(_onTopologyChanged);
    topology.dispose();
    HardwareKeyboard.instance.removeHandler(inputRouter.handleKeyEvent);
    codeSubscription?.cancel();
    shortcutSubscription?.cancel();
    productScanRepeats?.close();
    inputRouter.dispose();
    paymentReference.dispose();
    paymentAmount.dispose();
    ordersSearchDebounce?.cancel();
    ordersSearchController.dispose();
    ordersSearchFocus.dispose();
    commandSearchFocus.dispose();
    updateService.dispose();
    super.dispose();
  }

  /// Publica a falha no alerta global, que sempre traz o botão de fechar.
  ///
  /// A mensagem do backend é repassada literalmente: uma inconsistência de
  /// caixa ("caixa já aberto em outro terminal", "sangria divergente") precisa
  /// chegar ao operador exatamente como o servidor a descreveu.
  @override
  void _error(Object error, {String? title, String? action}) {
    final center = ErrorCenterScope.read(context);
    if (error is ApiException) {
      center.reportApi(error, title: title, recommendedAction: action);
      return;
    }
    if (error is PrinterCommunicationException) {
      center.report(
        AppError(
          title: title ?? 'Falha ao comunicar com a impressora',
          message: error.message,
          origin: AppErrorOrigin.peripheral,
          severity: AppErrorSeverity.warning,
          recommendedAction: action ?? error.recommendedAction,
          dedupeKey: 'printer-communication',
        ),
      );
      return;
    }
    center.reportUnexpected(error, title: title);
  }

  /// Reporta falhas de abertura, fechamento e movimentos de caixa.
  ///
  /// A operação só é considerada concluída depois da confirmação do servidor;
  /// qualquer recusa vira um alerta que o operador fecha para corrigir os
  /// dados e repetir.
  @override
  void _cashError(Object error, String operation) => _error(
    error,
    title: 'Não foi possível $operation',
    action: 'Feche este alerta, revise os dados e tente novamente.',
  );

  @override
  Future<T?> _work<T>(
    Future<T> Function() action, {
    String? errorTitle,
    void Function(Object error)? onError,
  }) async {
    if (busy) return null;
    setState(() => busy = true);
    try {
      return await action();
    } catch (error) {
      if (mounted) {
        if (onError != null) {
          onError(error);
        } else {
          _error(error, title: errorTitle);
        }
      }
      return null;
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  /// Executa uma impressão FORA da trava de operação da tela.
  ///
  /// `_work` existe para impedir o operador de disparar duas operações de
  /// venda ao mesmo tempo, e por isso ele DESISTE (`if (busy) return null`)
  /// quando já há uma em curso. Papel de venda concluída não pode obedecer a
  /// essa trava: o DANFE sai por uma espera em segundo plano — a autorização
  /// da SEFAZ chega segundos depois do clique — e nesse intervalo o operador
  /// já começou a próxima venda. Com `busy` verdadeiro, `_work` devolvia
  /// `null`, o `if (printJob == null) return;` seguinte engolia o caso, e o
  /// cupom fiscal simplesmente não existia: sem erro, sem fila, sem papel.
  ///
  /// Falha continua sendo mostrada — o que não pode é desaparecer.
  @override
  Future<bool> _printingStep(
    Future<void> Function() action, {
    required String title,
  }) async {
    try {
      await action();
      return true;
    } catch (error) {
      if (mounted) _error(error, title: title);
      return false;
    }
  }

  @override
  Future<void> _openTable(Map<String, dynamic> table) async {
    setState(() {
      selectedTable = table;
      flowStep = 'table_details';
    });
  }

  /// Autoriza a divergência do caixa com a senha de ações do restaurante.
  ///
  /// Com rede, a senha vai ao servidor como sempre. Sem rede, ela é conferida
  /// aqui contra o hash já sincronizado e o que sobe é uma **prova** de que
  /// este terminal conhece esse hash — a senha em texto nunca é gravada na
  /// fila. Sem isto, um caixa que fechasse com diferença ficava travado até a
  /// internet voltar, com o operador impedido de encerrar o turno.
  @override
  // Consumido pelas seções de caixa via declaração abstrata.
  Future<Map<String, dynamic>> _approveWithCashPassword({
    required String reason,
    required String password,
  }) async {
    final sessionId = '${cashSession!['id']}';
    final cashAuth = widget.controller.repository.cashAuth;
    final restaurant = restaurantId;

    if (api.syncStatus.hasConnection ||
        cashAuth == null ||
        restaurant == null) {
      return api.post(
        '/cash-register/$sessionId/approve/',
        body: {'reason': reason, 'cash_password': password},
        accessToken: token,
      );
    }

    if (!await cashAuth.verify(password, restaurantId: restaurant)) {
      throw const ApiException('Senha de ações do caixa inválida.');
    }
    final nonce = LocalId.uuid();
    final proof = await cashAuth.passwordProof(
      restaurantId: restaurant,
      cashRegisterId: sessionId,
      nonce: nonce,
    );
    if (proof == null) {
      throw const ApiException(
        'A senha de ações do caixa ainda não foi sincronizada neste '
        'terminal. Conecte-se uma vez para autorizar sem internet.',
      );
    }
    return api.post(
      '/cash-register/$sessionId/approve/',
      body: {
        'reason': reason,
        'cash_password_proof': proof,
        'proof_nonce': nonce,
      },
      accessToken: token,
      localContext: {'approver_name': widget.controller.session?.user.name},
    );
  }

  /// Monta o recibo do cliente com os dados que este terminal já tem.
  ///
  /// Restaurante, itens e recebimentos vêm do SQLite local, então o cupom sai
  /// completo mesmo com a rede fora — inclusive os pagamentos que ainda estão
  /// na fila.
}
