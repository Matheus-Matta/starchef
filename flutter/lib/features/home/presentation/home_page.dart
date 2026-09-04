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
import 'product_catalog_panel.dart';
import 'table_details_panel.dart';

part 'home_page_cash.dart';
part 'home_page_commands.dart';
part 'home_page_orders.dart';
part 'home_page_payment.dart';
part 'home_page_receipt.dart';
part 'home_page_shared.dart';
part 'home_page_fiscal.dart';

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
        _CommandSection,
        _FiscalSection,
        _OrdersSection,
        _PaymentSection,
        _ReceiptSection {
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
  double get defaultServiceFeePercent =>
      _number(selectedRestaurant?['default_service_fee_percent']);

  bool loading = true;

  /// Recarga em segundo plano: os dados estão sendo atualizados, mas a tela
  /// atual continua utilizável.
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
  String search = '';
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
  List<Map<String, dynamic>> restaurants = [];
  List<Map<String, dynamic>> products = [];
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
  String? selectedOrderItemId;
  @override
  List<Map<String, dynamic>> paymentMethods = [];
  @override
  List<Map<String, dynamic>> registeredPayments = [];
  @override
  List<Map<String, dynamic>> orders = [];
  @override
  bool ordersLoading = false;
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
  late final TerminalTopology topology;

  /// O controlador central de entrada: teclado, leitor USB, leitor serial e
  /// área de transferência entram por aqui e saem como o MESMO evento.
  late final PdvInputRouter inputRouter;
  CodeLookupService? codeLookup;
  StreamSubscription<ScannedCode>? codeSubscription;
  StreamSubscription<PdvShortcut>? shortcutSubscription;

  /// Enquanto o modal de configuração de produto está aberto, uma nova leitura
  /// do MESMO produto soma quantidade lá dentro em vez de abrir outro modal.
  StreamController<void>? productScanRepeats;
  String? scanningProductId;
  NetworkSyncStatus networkStatus = const NetworkSyncStatus(
    phase: NetworkSyncPhase.unknown,
  );
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

  PdvDestination get _selectedDestination {
    if (flowStep == 'scale-workstation') return PdvDestination.scale;
    if (flowStep == 'orders') return PdvDestination.orders;
    if (flowStep == 'table_details' ||
        (flowStep == 'context' && orderType != 'command')) {
      return PdvDestination.tables;
    }
    return PdvDestination.menu;
  }

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

  // ───────────────────────────────── entrada (teclado, leitor, colar) ──

  /// Em que tela o operador está — é o que decide como um código é lido.
  PdvScreen get _currentScreen {
    if (flowStep == 'scale-workstation') return PdvScreen.scale;
    if (flowStep == 'orders') return PdvScreen.orders;
    if (flowStep == 'payment') return PdvScreen.payment;
    if (activeOrder != null) return PdvScreen.order;
    if (flowStep == 'context' || flowStep == 'table_details') {
      return PdvScreen.context;
    }
    return PdvScreen.home;
  }

  /// O cursor está dentro de um campo de texto?
  ///
  /// Com um campo focado o teclado é dele: o leitor escreve ali como qualquer
  /// digitação, em vez de a tela interpretar o código por conta própria.
  bool get _hasTextFocus {
    final focus = FocusManager.instance.primaryFocus?.context;
    if (focus == null) return false;
    return focus.widget is EditableText ||
        focus.findAncestorWidgetOfExactType<EditableText>() != null;
  }

  /// Há um diálogo aberto por cima desta página?
  ///
  /// A rota da página deixa de ser a corrente quando um modal sobe — é o
  /// sinal mais confiável, e não depende de cada `showDialog` do arquivo
  /// lembrar de avisar.
  bool get _hasModalAbove {
    final route = ModalRoute.of(context);
    return route != null && !route.isCurrent;
  }

  PdvInputContext _readInputContext() => PdvInputContext(
    screen: _currentScreen,
    hasTextFocus: _hasTextFocus,
    hasModal: _hasModalAbove,
    // O único modal que entende código é o de configuração de produto: ler o
    // mesmo item de novo soma quantidade lá dentro.
    modalAcceptsScanner: scanningProductId != null,
    hasOrder: activeOrder != null,
  );

  /// A consulta de códigos, quando o armazenamento local já está ligado.
  ///
  /// Antes do login não há banco local, e ler um código nesse momento não faz
  /// sentido nenhum — daí o nulo em vez de uma exceção.
  CodeLookupService? get _codeLookup {
    final gateway = api.localStore;
    if (gateway == null) return null;
    return codeLookup ??= CodeLookupService(gateway);
  }

  /// Um código chegou — de onde quer que tenha vindo.
  Future<void> _onCodeScanned(ScannedCode scanned) async {
    switch (_currentScreen) {
      case PdvScreen.home:
        await _openOrderFromCommandCode(scanned.value);
      case PdvScreen.context:
        // A busca em memória (por número/código exato da lista já filtrada)
        // continua servindo a aba Comandas, que tem seu próprio campo de
        // busca e convive bem com múltiplos resultados. A aba Mesas não tem
        // campo de busca nenhum, então usa a mesma consulta ao banco local
        // que a tela inicial usa — robusta mesmo com `commands` desatualizado.
        if (orderType == 'command') {
          _onCommandSearchSubmitted(scanned.value);
        } else {
          await _openOrderFromCommandCode(scanned.value);
        }
      case PdvScreen.order:
        await _addProductFromCode(scanned.value);
      case PdvScreen.orders:
        // Bipar uma comanda abre direto o pedido em aberto dela; qualquer
        // outro código (produto, número de pedido) só preenche a busca da
        // lista, como antes.
        await _openOrderFromCommandCode(
          scanned.value,
          onNotFound: () {
            ordersSearchController.text = scanned.value;
            setState(() => orderSearch = scanned.value);
          },
        );
      case PdvScreen.payment:
      case PdvScreen.cash:
      case PdvScreen.settings:
      case PdvScreen.scale:
        break;
    }
  }

  /// Acha a comanda pelo código lido e abre o pedido em aberto dela.
  ///
  /// Usada pela tela inicial, pela aba Mesas e pela lista de Pedidos — sempre
  /// que a tela não tem um jeito melhor de tratar um código que não é
  /// comanda. Sem `onNotFound`, o silêncio é deliberado: um aviso a cada
  /// leitura sem correspondência transformaria uma pilha de cartões
  /// conferidos rapidamente em uma sequência de alertas para fechar.
  ///
  /// Também não procura produto aqui: um EAN lido por engano não pode
  /// disparar uma ação inesperada nessas telas.
  Future<void> _openOrderFromCommandCode(
    String code, {
    VoidCallback? onNotFound,
  }) async {
    final lookup = _codeLookup;
    if (lookup == null) {
      onNotFound?.call();
      return;
    }
    final resolution = await lookup.findCommand(code);
    final command = resolution.command;
    if (command == null) {
      onNotFound?.call();
      return;
    }
    final orderId = '${command['current_order_id'] ?? ''}';
    if (orderId.isEmpty) {
      onNotFound?.call();
      return;
    }
    final local = commands.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == '${command['id']}',
      orElse: () => null,
    );
    await _openCommand(local ?? command);
  }

  /// Edição do pedido: acha o produto e abre a configuração dele.
  Future<void> _addProductFromCode(String code) async {
    final lookup = _codeLookup;
    if (lookup == null) return;
    // Leitura repetida com o modal aberto: soma lá dentro.
    if (scanningProductId != null) {
      final repeated = await lookup.findProduct(
        code,
        restaurantId: restaurantId,
        orderType: orderType,
      );
      if ('${repeated.product?['id'] ?? ''}' == scanningProductId) {
        productScanRepeats?.add(null);
      }
      return;
    }

    final resolution = await lookup.findProduct(
      code,
      restaurantId: restaurantId,
      orderType: orderType,
    );
    final product = resolution.product;
    if (product == null) return;

    // Quem decide entre somar uma unidade e abrir o modal é
    // `_configureProduct`: produto sem escolha soma direto, com variação ou
    // adicional a pergunta continua. Duplicar a regra aqui deixava a leitura
    // do EAN pular as recusas que ela faz (pedido fechado, caixa fechado,
    // produto por peso).
    await _configureProduct(product);
  }

  bool _productHasChoices(Map<String, dynamic> product) {
    bool active(List? list) => (list ?? const []).whereType<Map>().any(
      (item) => item['is_active'] != false,
    );
    return active(product['variations'] as List?) ||
        active(product['addons'] as List?);
  }

  /// Soma uma unidade ao item pendente. O servidor agrupa itens pendentes
  /// iguais, e o armazenamento local passou a agrupar na mesma hora.
  Future<void> _addOneMoreOf(Map<String, dynamic> product) async {
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          'quantity': 1,
          'variations': const [],
          'addons': const [],
          'expected_unit_price': OrderPresenter.expectedUnitPrice(
            product,
          ).toStringAsFixed(2),
          'customer_note': '',
        },
        accessToken: token,
      );
      await _refreshOrder();
    });
  }

  /// Executa a ação de um atalho.
  Future<void> _onShortcut(PdvShortcut shortcut) async {
    switch (shortcut.id) {
      case PdvAction.help:
        await _openHelp();
      case PdvAction.readClipboard:
        await inputRouter.readFromClipboard();
      case PdvAction.home:
      case PdvAction.newSale:
        if (await _confirmLeavingPendingItems()) await _goHome();
      case PdvAction.orders:
        await _navigateTo(PdvDestination.orders);
      case PdvAction.refresh:
        await _load();
      case PdvAction.cashCenter:
        await _openCashCenter();
      case PdvAction.pickCommand:
        setState(() {
          orderType = 'command';
          commandSearch = '';
          flowStep = 'context';
        });
      case PdvAction.back:
        _goBack();
      case PdvAction.focusSearch:
        _focusPageSearch();
      case PdvAction.sendToKitchen:
        await _sendPendingFromShortcut();
      case PdvAction.payment:
        await _preparePaymentPage();
      case PdvAction.printReceipt:
        await _printCustomerReceipt();
      case PdvAction.moveSelectionUp:
        _moveItemSelection(-1);
      case PdvAction.moveSelectionDown:
        _moveItemSelection(1);
      case PdvAction.increaseQuantity:
        await _changeSelectedQuantity(1);
      case PdvAction.decreaseQuantity:
        await _changeSelectedQuantity(-1);
      case PdvAction.removeItem:
        await _removeSelectedItem();
      case PdvAction.confirm:
        await _confirmPrimaryAction();
    }
  }

  /// Confirma o descarte dos recebimentos que ainda não subiram.
  Future<void> _confirmLeavingPayment() async {
    final count = stagedPayments.length;
    final discard = await showDialog<bool>(
      context: context,
      builder: (ctx) => AppDialog(
        title: const Text('Descartar os recebimentos desta tela?'),
        content: Text(
          count == 1
              ? 'Há 1 recebimento montado que ainda não foi enviado. Voltar '
                    'agora o descarta — o pedido continua em aberto.'
              : 'Há $count recebimentos montados que ainda não foram '
                    'enviados. Voltar agora os descarta — o pedido continua '
                    'em aberto.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Continuar recebendo'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Descartar e voltar'),
          ),
        ],
      ),
    );
    if (discard != true || !mounted) return;
    setState(() {
      registeredPayments = registeredPayments
          .where((payment) => payment['_staged'] != true)
          .toList();
      flowStep = 'order';
    });
  }

  /// Sair do pedido com itens ainda não enviados exige confirmação.
  ///
  /// F3 e Ctrl + N ficam ao lado de teclas usadas o tempo todo, e um toque
  /// errado apagaria da tela itens que a cozinha nunca recebeu — sem que
  /// ninguém percebesse até o cliente cobrar.
  Future<bool> _confirmLeavingPendingItems() async {
    if (activeOrder == null) return true;
    final pending = orderItems
        .where((item) => item['status'] == 'pending')
        .length;
    if (pending == 0) return true;
    final answer = await showDialog<bool>(
      context: context,
      builder: (ctx) => AppDialog(
        title: const Text('Sair com itens não enviados?'),
        content: Text(
          pending == 1
              ? 'Há 1 item lançado que ainda não foi para a cozinha. '
                    'Ele continua no pedido, mas você sai da tela dele.'
              : 'Há $pending itens lançados que ainda não foram para a '
                    'cozinha. Eles continuam no pedido, mas você sai da tela '
                    'dele.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Continuar no pedido'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sair mesmo assim'),
          ),
        ],
      ),
    );
    return answer == true;
  }

  // ─────────────────────────────────── seleção de item por teclado ──

  /// A lista de itens na MESMA ordem em que o painel a desenha.
  ///
  /// As setas precisam andar na ordem que o operador vê; percorrer a lista
  /// bruta faria o cursor pular de um bloco para o outro sem motivo aparente.
  List<Map<String, dynamic>> get _itemsInDisplayOrder => [
    ...orderItems.where((item) => item['status'] != 'pending'),
    ...orderItems.where((item) => item['status'] == 'pending'),
  ];

  Map<String, dynamic>? get _selectedOrderItem {
    final id = selectedOrderItemId;
    if (id == null) return null;
    for (final item in orderItems) {
      if ('${item['id']}' == id) return item;
    }
    return null;
  }

  /// Move o cursor. Sem seleção, a primeira seta escolhe a ponta certa da
  /// lista — descer começa no primeiro item, subir no último.
  void _moveItemSelection(int delta) {
    final items = _itemsInDisplayOrder;
    if (items.isEmpty) {
      setState(() => selectedOrderItemId = null);
      return;
    }
    final current = items.indexWhere(
      (item) => '${item['id']}' == selectedOrderItemId,
    );
    final next = current < 0
        ? (delta > 0 ? 0 : items.length - 1)
        : (current + delta).clamp(0, items.length - 1);
    setState(() => selectedOrderItemId = '${items[next]['id']}');
    _revealSelectedItem();
  }

  void _selectOrderItem(Map<String, dynamic> item) {
    setState(() => selectedOrderItemId = '${item['id']}');
  }

  /// Rola a lista até a linha selecionada quando ela sai da área visível.
  void _revealSelectedItem() {
    final id = selectedOrderItemId;
    if (id == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = OrderCartPanel.contextOfItem(id);
      if (target == null) return;
      unawaited(
        Scrollable.ensureVisible(
          target,
          alignment: .5,
          duration: const Duration(milliseconds: 140),
        ),
      );
    });
  }

  /// `+` e `-` sobre o item selecionado.
  ///
  /// Só item pendente: um já despachado descreve o que a cozinha recebeu, e
  /// mudar a quantidade dele reescreveria o passado sem ninguém na produção
  /// ficar sabendo. Chegando a zero, a tecla vira o cancelamento — que exige
  /// motivo e deixa registro, em vez de apagar em silêncio.
  Future<void> _changeSelectedQuantity(int delta) async {
    final item = _selectedOrderItem;
    if (item == null) return;
    await _changeItemQuantity(item, delta);
  }

  /// Soma [delta] unidades a um item. Serve às teclas `+`/`-` e ao contador
  /// que fica no próprio cartão da lista — o mesmo caminho, com as mesmas
  /// recusas, para os dois gestos não divergirem.
  Future<void> _changeItemQuantity(Map<String, dynamic> item, int delta) async {
    if (busy || activeOrder == null) return;
    if ('${item['status'] ?? ''}' != 'pending') {
      _error(
        const ApiException(
          'Este item já foi para a produção. Cancele-o (Delete) se precisar '
          'tirá-lo da conta.',
        ),
      );
      return;
    }
    if ('${item['pricing_unit'] ?? 'unit'}' == 'kg') {
      _error(
        const ApiException(
          'Produto vendido por peso: a quantidade vem da balança.',
        ),
      );
      return;
    }
    final quantity = ValueFormatters.number(item['quantity']) + delta;
    if (quantity <= 0) {
      // Zero é cancelamento, e cancelamento pede motivo e deixa registro.
      await _voidItem(item);
      if (mounted && '${item['id']}' == selectedOrderItemId) {
        setState(() => selectedOrderItemId = null);
      }
      return;
    }
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/${item['id']}/quantity/',
        body: {'quantity': quantity},
        accessToken: token,
      );
      await _refreshOrder();
      return activeOrder ?? <String, dynamic>{};
    });
  }

  /// Delete sobre o item selecionado.
  ///
  /// Reusa o cancelamento normal, que já pede motivo e — para item despachado
  /// — passa pela permissão e pelo cupom de cancelamento na cozinha. Uma tecla
  /// não pode ter um caminho mais curto do que o botão.
  Future<void> _removeSelectedItem() async {
    final item = _selectedOrderItem;
    if (item == null || busy) return;
    await _voidItem(item);
    if (mounted) setState(() => selectedOrderItemId = null);
  }

  // ────────────────────────────────────────────── ação principal (Enter) ──

  /// O que o Enter confirma nesta tela.
  ///
  /// Só chega aqui quando NÃO há modal aberto nem campo focado — nesses dois
  /// casos o Enter pertence a quem tem o foco, e é assim que ele continua
  /// funcionando dentro dos diálogos sem nenhum caso especial.
  Future<void> _confirmPrimaryAction() async {
    switch (_currentScreen) {
      case PdvScreen.order:
        if (activeOrder == null || orderItems.isEmpty) return;
        await _finishOrder();
      case PdvScreen.context:
        // Uma comanda filtrada e só uma: confirmar é abrir. Com várias, o
        // Enter não escolhe por ninguém.
        if (orderType != 'command') return;
        final visible = visibleCommands;
        if (visible.length == 1) await _openCommand(visible.first);
      case PdvScreen.payment:
        await _confirmPaymentFromKeyboard();
      case PdvScreen.home:
      case PdvScreen.orders:
      case PdvScreen.cash:
      case PdvScreen.settings:
      case PdvScreen.scale:
        break;
    }
  }

  /// Enter na tela de pagamento.
  ///
  /// A regra é a mesma do botão, e de propósito: enquanto faltar dado
  /// obrigatório, a tecla não conclui nada. Um Enter que cobra sozinho seria
  /// pior do que um Enter que não faz nada, porque o operador só descobriria
  /// depois — com o cliente já do outro lado do balcão.
  Future<void> _confirmPaymentFromKeyboard() async {
    if (activeOrder == null || busy) return;
    // Já pago por inteiro: confirmar é concluir.
    if (remainingTotal <= .009) {
      await _completePaidOrder();
      return;
    }
    // Falta valor: só registra o recebimento digitado, e só se ele existir e
    // houver forma de pagamento escolhida.
    if (selectedPaymentMethod == null || paymentValue <= 0) return;
    _addSplitPayment();
  }

  /// Leva o cursor para a busca da tela atual.
  void _focusPageSearch() {
    if (_currentScreen == PdvScreen.orders) {
      ordersSearchFocus.requestFocus();
      return;
    }
    if (_currentScreen == PdvScreen.context) {
      commandSearchFocus.requestFocus();
    }
  }

  /// F9: manda para a produção só o que ainda está pendente.
  ///
  /// Sem itens pendentes a tecla não faz nada — e não avisa: apertar F9 duas
  /// vezes é comum, e a segunda não pode virar um alerta.
  Future<void> _sendPendingFromShortcut() async {
    if (activeOrder == null || busy) return;
    final pending = orderItems
        .where((item) => item['status'] == 'pending')
        .toList();
    if (pending.isEmpty) return;
    await _work(() async {
      await _sendPendingItemsToKitchen(pending);
      return activeOrder ?? <String, dynamic>{};
    });
    if (mounted) await _refreshOrder();
  }

  Future<void> _openHelp() async {
    final serial = topology.config;
    await PdvHelpDialog.show(
      context,
      screen: _currentScreen,
      hasOrder: activeOrder != null,
      scannerStatus: ScannerStatus(
        connected: false,
        detail: serial == null
            ? 'A estação de balança é quem cuida do leitor serial.'
            : 'Vincule o leitor serial em Balança rápida › Equipamentos.',
      ),
      lastCode: inputRouter.lastCode,
      onTestCode: _describeCode,
    );
  }

  /// Diz o que ACONTECERIA com um código, sem executar nada.
  Future<String> _describeCode(String code) async {
    final screen = _currentScreen;
    if (!screen.readsCodes) {
      return '${screen.label}: códigos são ignorados aqui, de propósito.';
    }
    final lookup = _codeLookup;
    if (lookup == null) {
      return 'O armazenamento local ainda não está pronto nesta sessão.';
    }
    final product = await lookup.findProduct(
      code,
      restaurantId: restaurantId,
      orderType: orderType,
    );
    if (product.found) {
      return 'Produto "${product.product?['name']}" — encontrado pelo '
          '${product.matchedFieldLabel}.'
          '${screen == PdvScreen.order ? ' Nesta tela, abriria a configuração do item.' : ' Esta tela não lança produtos.'}';
    }
    final command = await lookup.findCommand(code);
    if (command.found) {
      final orderId = '${command.command?['current_order_id'] ?? ''}';
      return 'Comanda ${command.command?['number']} — encontrada pelo '
          '${command.matchedFieldLabel}. '
          '${orderId.isEmpty ? 'Sem pedido em aberto.' : 'Abriria o pedido em aberto dela.'}';
    }
    return 'Nenhuma comanda e nenhum produto com este código. '
        'Na operação, uma leitura assim não faz nada e não mostra aviso.';
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

  Future<void> _selectOrderType(String type) async {
    orderType = type;
    if (type == 'command') {
      setState(() {
        commandSearch = '';
        flowStep = 'context';
      });
      return;
    }
    if (type == 'takeaway' || type == 'delivery') {
      final customer = await _chooseCustomer(type);
      if (customer == null) {
        setState(() => orderType = null);
        return;
      }
      selectedCustomer = customer;
    }
    await _startOrder(type);
  }

  Future<Map<String, dynamic>?> _chooseCustomer(String type) async {
    List<Map<String, dynamic>> customers;
    try {
      customers = await _list(
        '/customers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 300,
        },
      );
    } catch (error) {
      if (mounted) _error(error);
      return null;
    }
    if (!mounted) return null;
    var search = '';
    return showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (context) => StatefulBuilder(
        builder: (context, update) {
          final filtered = customers.where((customer) {
            final term = search.trim().toLowerCase();
            return term.isEmpty ||
                '${customer['name']} ${customer['phone']} ${customer['document'] ?? ''}'
                    .toLowerCase()
                    .contains(term);
          }).toList();
          return AppDialog(
            title: Text(
              type == 'delivery'
                  ? 'Cliente do delivery'
                  : 'Cliente da retirada',
            ),
            content: SizedBox(
              width: 620,
              height: 480,
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          autofocus: true,
                          onChanged: (value) => update(() => search = value),
                          decoration: const InputDecoration(
                            labelText: 'Buscar cliente',
                            hintText: 'Nome, telefone ou CPF',
                            prefixIcon: Icon(Icons.search),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton.icon(
                        onPressed: () async {
                          final created = await _createCustomerDialog();
                          if (created != null && context.mounted) {
                            customers = [created, ...customers];
                            update(() {});
                            Navigator.pop(context, created);
                          }
                        },
                        icon: const Icon(Icons.person_add_alt_1),
                        label: const Text('Novo cliente'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: filtered.isEmpty
                        ? const Center(
                            child: Text(
                              'Nenhum cliente encontrado. Cadastre um novo cliente.',
                              textAlign: TextAlign.center,
                            ),
                          )
                        : ListView.separated(
                            itemCount: filtered.length,
                            separatorBuilder: (_, _) =>
                                const Divider(height: 1),
                            itemBuilder: (_, index) {
                              final customer = filtered[index];
                              return ListTile(
                                leading: const CircleAvatar(
                                  child: Icon(Icons.person_outline),
                                ),
                                title: Text('${customer['name']}'),
                                subtitle: Text('${customer['phone']}'),
                                trailing: const Icon(Icons.chevron_right),
                                onTap: () => Navigator.pop(context, customer),
                              );
                            },
                          ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Voltar'),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<Map<String, dynamic>?> _createCustomerDialog() async {
    final formKey = GlobalKey<FormState>();
    final name = TextEditingController();
    final phone = TextEditingController();
    final email = TextEditingController();
    final document = TextEditingController();
    final notes = TextEditingController();
    var saving = false;
    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AppDialog(
          title: const Text('Cadastrar cliente'),
          content: SizedBox(
            width: 560,
            child: Form(
              key: formKey,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    TextFormField(
                      controller: name,
                      autofocus: true,
                      decoration: const InputDecoration(
                        labelText: 'Nome completo',
                        helperText: 'Nome usado para identificar o cliente.',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Informe o nome do cliente.'
                          : null,
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: phone,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: 'Telefone',
                        helperText: 'Número para contato sobre o pedido.',
                      ),
                      validator: (value) =>
                          value == null || value.trim().isEmpty
                          ? 'Informe o telefone.'
                          : null,
                    ),
                    const SizedBox(height: 14),
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: email,
                            keyboardType: TextInputType.emailAddress,
                            decoration: const InputDecoration(
                              labelText: 'E-mail',
                              helperText: 'Opcional',
                            ),
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: TextFormField(
                            controller: document,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'CPF',
                              helperText: 'Opcional',
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
                    TextFormField(
                      controller: notes,
                      maxLines: 2,
                      decoration: const InputDecoration(
                        labelText: 'Observações internas',
                        helperText:
                            'Informações visíveis somente para a equipe.',
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(context),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: saving
                  ? null
                  : () async {
                      if (!formKey.currentState!.validate()) return;
                      update(() => saving = true);
                      try {
                        final customer = await api.post(
                          '/customers/',
                          body: {
                            'restaurant': restaurantId,
                            'name': name.text.trim(),
                            'phone': phone.text.trim(),
                            'email': email.text.trim(),
                            'document': document.text.trim(),
                            'internal_notes': notes.text.trim(),
                            'is_active': true,
                          },
                          accessToken: token,
                        );
                        if (context.mounted) Navigator.pop(context, customer);
                      } catch (error) {
                        if (context.mounted) _error(error);
                        update(() => saving = false);
                      }
                    },
              icon: saving
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: const Text('Cadastrar e selecionar'),
            ),
          ],
        ),
      ),
    );
    name.dispose();
    phone.dispose();
    email.dispose();
    document.dispose();
    notes.dispose();
    return result;
  }

  Future<void> _startOrder(String type) async {
    await _work(() async {
      selectedTable = null;
      activeOrder = await api.post(
        '/orders/',
        body: {
          'restaurant': restaurantId,
          'order_type': type,
          if (selectedCustomer != null) 'customer': selectedCustomer!['id'],
        },
        accessToken: token,
      );
      activeOrder = _completeOfflineOrder(activeOrder!, type: type);
      await _refreshOrder();
      flowStep = 'order';
    });
  }

  /// Relê o pedido da fonte operacional local.
  ///
  /// `api.get` é offline-first: responde do SQLite na hora e reconcilia com o
  /// servidor em paralelo (§3). Por isso não há mais dois caminhos aqui — o
  /// pedido criado offline e o pedido vindo do servidor moram no mesmo lugar.
  @override
  Future<void> _refreshOrder() async {
    if (activeOrder == null) return;
    try {
      activeOrder = await api.get(
        '/orders/${activeOrder!['id']}/',
        accessToken: token,
      );
    } on ApiException catch (error) {
      if (!error.isConnectivity) rethrow;
      if (mounted) _warnLocalOrderData();
    }
    final items = activeOrder!['items'] as List? ?? [];
    orderItems = items
        .cast<Map<String, dynamic>>()
        .where((item) => item['status'] != 'voided')
        .toList();
    // O total pode ter mudado aqui — a taxa de serviço do fechamento chega
    // pela sincronização, e é depois desta leitura que ela aparece.
    if (flowStep == 'payment') _refreshSuggestedPaymentAmount();
    if (mounted) setState(() {});
  }

  @override
  bool _isOfflinePending(Map<String, dynamic>? value) =>
      OrderPresenter.isOffline(value);

  @override
  Map<String, dynamic> _completeOfflineOrder(
    Map<String, dynamic> order, {
    required String type,
    Map<String, dynamic>? table,
    Map<String, dynamic>? command,
  }) {
    return OrderPresenter.completeOfflineOrder(
      order,
      restaurantId: restaurantId,
      type: type,
      table: table,
      command: command,
    );
  }

  Future<void> _configureProduct(Map<String, dynamic> product) async {
    if (const {
      'paid',
      'cancelled',
      'refunded',
    }.contains('${activeOrder?['status']}')) {
      _error(
        const ApiException(
          'Este pedido já foi concluído e está disponível somente para consulta.',
        ),
      );
      return;
    }
    if (cashSession == null) {
      _error(
        const ApiException('Abra o caixa antes de iniciar pedidos no PDV.'),
      );
      return;
    }
    if (activeOrder == null) {
      setState(() {
        orderType = 'command';
        commandSearch = '';
        flowStep = 'context';
      });
      return;
    }
    if (!mounted) return;
    if (isProductSoldByWeight(product)) {
      await _weighProduct(product);
      return;
    }
    // Produto sem variação e sem adicional não tem NADA a perguntar: clicar
    // nele na lista (ou bipar o EAN) soma uma unidade direto, e o ajuste fino
    // fica no contador do próprio cartão, na lista do pedido. O modal existia
    // para escolher, e abrir uma janela de confirmação para um refrigerante
    // custava dois gestos por unidade num balcão com fila.
    if (!_productHasChoices(product)) {
      await _addOneMoreOf(product);
      return;
    }
    // Enquanto este modal estiver aberto, ler o MESMO produto de novo soma
    // quantidade aqui dentro em vez de abrir um segundo modal por cima.
    //
    // O `finally` não é zelo: se o diálogo falhasse com a marca ligada, toda
    // leitura seguinte seria interpretada como "repetição do produto X" e
    // nenhum outro item entraria no pedido.
    final repeats = StreamController<void>.broadcast();
    ProductConfigResult? config;
    try {
      productScanRepeats = repeats;
      scanningProductId = '${product['id']}';
      config = await showProductConfigDialog(
        context,
        product,
        repeatedScans: repeats.stream,
      );
    } finally {
      scanningProductId = null;
      productScanRepeats = null;
      await repeats.close();
    }
    if (config == null) return;
    // Cópia não-nula: o `finally` acima impede o compilador de promover o tipo.
    final chosen = config;
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          'quantity': chosen.quantity.round(),
          'variations': chosen.variationId == null ? [] : [chosen.variationId],
          'addons': chosen.addonIds,
          'expected_unit_price': OrderPresenter.expectedUnitPrice(
            product,
            variationIds: chosen.variationId == null
                ? const []
                : [chosen.variationId!],
            addonIds: chosen.addonIds,
          ).toStringAsFixed(2),
          'customer_note': chosen.customerNote,
        },
        accessToken: token,
      );
      // O item já foi lançado e os totais recalculados pelo
      // `OrderRepository`; a tela apenas relê o pedido do banco local.
      await _refreshOrder();
    });
  }

  Future<void> _weighProduct(Map<String, dynamic> product) async {
    final scales = await _list(
      '/scales/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    );
    if (!mounted) return;
    String? scaleId = scales.length == 1 ? '${scales.first['id']}' : null;
    Map<String, dynamic>? reading;
    double weight = 0;
    bool readingScale = false;
    String readingMessage = scales.isEmpty
        ? 'Nenhuma balança ativa cadastrada.'
        : 'Selecione a balança e solicite a leitura.';
    final manualWeight = TextEditingController();
    final note = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => CallbackShortcuts(
          bindings: {
            // Enter lança o item pesado, a mesma condição do botão. O atalho
            // precisa do nó de foco abaixo dele: senão o foco fica no escopo
            // da rota e a tecla passa por cima sem tocar em nada.
            for (final key in const [
              LogicalKeyboardKey.enter,
              LogicalKeyboardKey.numpadEnter,
            ])
              SingleActivator(key): () {
                if (weight > 0) Navigator.pop(context, true);
              },
          },
          child: Focus(
            autofocus: true,
            child: AppDialog(
              title: Row(
                children: [
                  const Icon(Icons.scale_outlined),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      '${product['name']} · ${_money(product['current_price'])}/kg',
                    ),
                  ),
                ],
              ),
              content: SizedBox(
                width: 460,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<String?>(
                      initialValue: scaleId,
                      isExpanded: true,
                      decoration: const InputDecoration(
                        labelText: 'Balança',
                        helperText:
                            'Selecione o equipamento que realizará a pesagem.',
                      ),
                      items: scales
                          .map(
                            (scale) => DropdownMenuItem(
                              value: '${scale['id']}',
                              child: Text(
                                '${scale['name']} · ${scale['port'] ?? scale['protocol'] ?? ''}',
                              ),
                            ),
                          )
                          .toList(),
                      onChanged: (value) => update(() {
                        scaleId = value;
                        reading = null;
                        weight = 0;
                        readingMessage =
                            'Clique em “Ler balança” para buscar o peso.';
                      }),
                    ),
                    const SizedBox(height: 18),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(vertical: 22),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surfaceContainer,
                        borderRadius: AppTheme.radius,
                        border: Border.all(
                          color: weight > 0
                              ? Theme.of(context).colorScheme.primary
                              : Theme.of(context).dividerColor,
                        ),
                      ),
                      child: Column(
                        children: [
                          Text(
                            weight.toStringAsFixed(3),
                            style: TextStyle(
                              fontSize: 42,
                              fontWeight: FontWeight.w900,
                              color: weight > 0
                                  ? Theme.of(context).colorScheme.primary
                                  : Theme.of(
                                      context,
                                    ).colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const Text(
                            'kg',
                            style: TextStyle(fontWeight: FontWeight.w700),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      readingMessage,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton.icon(
                            onPressed: scaleId == null || readingScale
                                ? null
                                : () async {
                                    update(() => readingScale = true);
                                    try {
                                      final result = await api.get(
                                        '/scales/$scaleId/latest-reading/',
                                        accessToken: token,
                                      );
                                      final value = _number(
                                        result['net_weight_kg'] ??
                                            result['weight_kg'],
                                      );
                                      update(() {
                                        reading = result;
                                        weight = value;
                                        manualWeight.clear();
                                        readingMessage =
                                            result['is_stable'] == false
                                            ? 'Leitura recebida, mas ainda instável.'
                                            : 'Leitura estável recebida da balança.';
                                      });
                                    } on ApiException catch (error) {
                                      update(
                                        () => readingMessage = error.message,
                                      );
                                      if (mounted) {
                                        showAppError(this.context, error);
                                      }
                                    } finally {
                                      update(() => readingScale = false);
                                    }
                                  },
                            icon: readingScale
                                ? const SizedBox(
                                    width: 17,
                                    height: 17,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.refresh),
                            label: Text(
                              readingScale ? 'Lendo...' : 'Ler balança',
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: manualWeight,
                            keyboardType: const TextInputType.numberWithOptions(
                              decimal: true,
                            ),
                            decoration: const InputDecoration(
                              labelText: 'Peso manual',
                              suffixText: 'kg',
                            ),
                            onChanged: (value) => update(() {
                              reading = null;
                              weight =
                                  double.tryParse(value.replaceAll(',', '.')) ??
                                  0;
                              readingMessage = weight > 0
                                  ? 'Peso informado manualmente.'
                                  : 'Leia a balança ou informe o peso.';
                            }),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: note,
                      maxLines: 2,
                      decoration: const InputDecoration(
                        labelText: 'Observação',
                        hintText: 'Ex.: retirar excesso de gordura',
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Total estimado',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          _money(weight * _number(product['current_price'])),
                          style: const TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Cancelar'),
                ),
                FilledButton(
                  onPressed: weight > 0
                      ? () => Navigator.pop(context, true)
                      : null,
                  child: const Text('Adicionar ao pedido (Enter)'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (accepted != true) return;
    await _work(() async {
      await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          if (reading != null)
            'scale_reading': reading!['id']
          else
            'weight_kg': weight.toStringAsFixed(3),
          'customer_note': note.text.trim(),
          'variations': [],
          'addons': [],
        },
        accessToken: token,
      );
      await _refreshOrder();
    });
  }

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

  Future<void> _finishOrder() async {
    if (activeOrder == null || orderItems.isEmpty) return;
    var chargeService = activeOrder?['service_fee_enabled'] != false;
    final nextStep = await showDialog<String>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AppDialog(
          title: const Text('Revisar pedido'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Subtotal', style: Theme.of(context).textTheme.labelLarge),
                const SizedBox(height: 4),
                Text(
                  _money(activeOrder?['subtotal']),
                  style: const TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 12),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: chargeService,
                  onChanged: (value) =>
                      setDialogState(() => chargeService = value ?? true),
                  title: const Text('Cobrar taxa de serviço'),
                  subtitle: const Text(
                    'Desmarque para retirar a taxa deste pedido.',
                  ),
                ),
                if (chargeService && defaultServiceFeePercent > 0) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Taxa estimada (${defaultServiceFeePercent.toStringAsFixed(2).replaceAll('.', ',')}%): '
                    '${_money(_number(activeOrder?['subtotal']) * defaultServiceFeePercent / 100)}',
                  ),
                ],
                const SizedBox(height: 8),
                Text(
                  'Total estimado: ${_money(_number(activeOrder?['subtotal']) + (chargeService ? _number(activeOrder?['subtotal']) * defaultServiceFeePercent / 100 : 0) + _number(activeOrder?['delivery_fee']) - _number(activeOrder?['discount']))}',
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Voltar'),
            ),
            OutlinedButton.icon(
              onPressed: () => Navigator.pop(context, 'later'),
              icon: const Icon(Icons.schedule),
              label: const Text('Pagar depois'),
            ),
            // Sem `payments.manage`, o operador só pode mandar para a cozinha
            // e deixar o recebimento para quem tem a permissão de caixa.
            if (widget.controller.session!.user.canProcessPayments)
              FilledButton(
                onPressed: () => Navigator.pop(context, 'payment'),
                child: const Text('Ir para pagamento'),
              ),
          ],
        ),
      ),
    );
    if (nextStep == null) return;
    // "Pagar depois" manda os itens para a produção e devolve o operador ao
    // pedido: o cliente segue consumindo, então fechar aqui (status
    // `aguardando pagamento`) travaria o lançamento de novos itens. O
    // fechamento acontece só no caminho do pagamento.
    if (nextStep == 'later') {
      await _work(() async {
        final pending = orderItems
            .where((item) => item['status'] == 'pending')
            .toList();
        if (pending.isEmpty) return <String, dynamic>{};
        // O `OrderRepository` já marcou a rodada como enviada e gravou; a
        // tela relê logo abaixo.
        await _sendPendingItemsToKitchen(pending);
        return activeOrder ?? <String, dynamic>{};
      });
      if (!mounted) return;
      await _refreshOrder();
      if (mounted) setState(() => flowStep = 'order');
      return;
    }
    final closed = await _work(() async {
      final hasPendingItems = orderItems.any(
        (item) => item['status'] == 'pending',
      );
      if (hasPendingItems) {
        await _sendPendingItemsToKitchen(
          orderItems.where((item) => item['status'] == 'pending').toList(),
        );
        await _refreshOrder();
      }
      // O fechamento (taxa de serviço, desconto, total) é aplicado pelo
      // `OrderRepository` com a MESMA conta usada aqui — `expected_total`
      // acompanha para o servidor conferir quando a operação subir.
      activeOrder = await api.post(
        '/orders/${activeOrder!['id']}/close/',
        body: {
          'discount': activeOrder?['discount'] ?? 0,
          'service_fee_enabled': chargeService,
        },
        accessToken: token,
      );
      await _refreshOrder();
      return activeOrder!;
    });
    if (closed == null) return;
    // A impressão fica só para depois do pagamento (cupom fiscal) ou para o
    // fluxo automático setorizado da cozinha — não existe "nota de
    // conferência" fora desses dois: aqui só falta o caixa seguir para o
    // teclado de pagamento.
    await _paymentDialog();
  }

  /// Autoriza a divergência do caixa com a senha de ações do restaurante.
  ///
  /// Com rede, a senha vai ao servidor como sempre. Sem rede, ela é conferida
  /// aqui contra o hash já sincronizado e o que sobe é uma **prova** de que
  /// este terminal conhece esse hash — a senha em texto nunca é gravada na
  /// fila. Sem isto, um caixa que fechasse com diferença ficava travado até a
  /// internet voltar, com o operador impedido de encerrar o turno.
  @override
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
          width: 42,
          height: 42,
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
            height: 44,
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
        'Pagamento',
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

  Widget _startPanel() {
    final options = [
      (
        'command',
        'Comanda',
        'Atendimento no salão ou cartão de comanda',
        Icons.qr_code_2,
      ),
      ('counter', 'Balcão', 'Consumo rápido no local', Icons.storefront),
      (
        'takeaway',
        'Retirada',
        'Pedido para viagem',
        Icons.shopping_bag_outlined,
      ),
      ('delivery', 'Delivery', 'Pedido para entrega', Icons.delivery_dining),
    ];
    final scheme = Theme.of(context).colorScheme;
    final availableTables = tables
        .where(
          (item) =>
              (item['active_commands'] as List? ?? const []).isEmpty &&
              item['status'] == 'free',
        )
        .length;
    final availableCommands = commands
        .where(
          (item) =>
              item['is_active'] != false &&
              item['status'] == 'free' &&
              item['current_order_id'] == null,
        )
        .length;
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Escolha o tipo de atendimento',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              AppStatusBadge(
                label: '${products.length} produtos ativos',
                icon: Icons.inventory_2_outlined,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _operationStat(
                  'MESAS LIVRES',
                  '$availableTables',
                  Icons.table_restaurant_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _operationStat(
                  'COMANDAS LIVRES',
                  '$availableCommands',
                  Icons.qr_code_2_outlined,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _operationStat(
                  'PEDIDOS CARREGADOS',
                  '${orders.length}',
                  Icons.receipt_long_outlined,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Divider(height: 1, color: scheme.outlineVariant),
          const SizedBox(height: 14),
          Expanded(
            child: GridView.builder(
              gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                maxCrossAxisExtent: 230,
                mainAxisExtent: 190,
                mainAxisSpacing: 12,
                crossAxisSpacing: 12,
              ),
              itemCount: options.length,
              itemBuilder: (_, index) {
                final option = options[index];
                return ShadCard(
                  padding: EdgeInsets.zero,
                  radius: AppTheme.radius,
                  shadows: const [],
                  columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      borderRadius: AppTheme.radius,
                      onTap: () => _selectOrderType(option.$1),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Container(height: 3, color: scheme.primary),
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Container(
                                        width: 42,
                                        height: 42,
                                        decoration: BoxDecoration(
                                          color: scheme.primaryContainer,
                                          borderRadius: AppTheme.radius,
                                        ),
                                        child: Icon(
                                          option.$4,
                                          color: scheme.primary,
                                          size: 21,
                                        ),
                                      ),
                                      const Spacer(),
                                      Text(
                                        '${index + 1}'.padLeft(2, '0'),
                                        style: TextStyle(
                                          color: scheme.onSurfaceVariant,
                                          fontSize: 10,
                                          fontWeight: FontWeight.w900,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const Spacer(),
                                  Text(
                                    option.$2,
                                    style: const TextStyle(
                                      fontSize: 17,
                                      fontWeight: FontWeight.w900,
                                    ),
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    option.$3,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 11,
                                      color: scheme.onSurfaceVariant,
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  Row(
                                    children: [
                                      Text(
                                        'INICIAR',
                                        style: TextStyle(
                                          color: scheme.primary,
                                          fontSize: 9,
                                          fontWeight: FontWeight.w900,
                                          letterSpacing: .8,
                                        ),
                                      ),
                                      const Spacer(),
                                      Icon(
                                        Icons.arrow_forward,
                                        size: 16,
                                        color: scheme.primary,
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget _operationStat(String label, String value, IconData icon) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 72,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: AppTheme.radius,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Row(
        children: [
          Icon(icon, size: 19, color: scheme.onSurfaceVariant),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  value,
                  style: const TextStyle(
                    fontSize: 19,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 8,
                    fontWeight: FontWeight.w900,
                    letterSpacing: .5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _catalog() {
    final filteredProducts = visibleProducts;
    return ProductCatalogPanel(
      products: filteredProducts,
      allProducts: products,
      categories: categories,
      selectedCategory: category,
      search: search,
      money: _money,
      onSearchChanged: (value) => setState(() => search = value),
      onCategoryChanged: (value) => setState(() => category = value),
      onProductPressed: _configureProduct,
    );
  }

  Widget _cart() => OrderCartPanel(
    selectedItemId: selectedOrderItemId,
    onSelectItem: _selectOrderItem,
    onChangeQuantity: _changeItemQuantity,
    order: activeOrder,
    table: selectedTable,
    command: selectedCommand,
    customer: selectedCustomer,
    items: orderItems,
    money: _money,
    onVoidItem: _voidItem,
    onFinish: _finishOrder,
    onPrint: _printCustomerReceipt,
    onCancel: widget.controller.session!.user.canCancelOrders
        ? _cancelOrder
        : null,
    onEmitInvoice:
        activeOrder == null ||
            !widget.controller.session!.user.canProcessPayments
        ? null
        : () => _emitFiscalInvoice(activeOrder!),
    onPrintInvoice:
        activeOrder == null ||
            !widget.controller.session!.user.canProcessPayments
        ? null
        : () => _reprintDanfe(activeOrder!),
    printing: printingReceipt,
    emittingInvoice: emittingInvoice,
  );
}
