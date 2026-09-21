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

import '../../../core/config/app_config.dart';
import '../../../core/errors/app_error.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/errors/app_error_host.dart';
import '../../../core/errors/notification_bell.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/formatters/cpf_formatter.dart';
import '../../../core/formatters/value_formatters.dart';
import '../../../core/storage/local_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/pdv_update_service.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../../core/widgets/app_dialog.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../../core/widgets/supervisor_close_dialog.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../devices/presentation/device_list_page.dart';
import '../../devices/presentation/print_queue_dialog.dart';
import '../../devices/presentation/printer_selection_dialog.dart';
import '../../devices/services/local_device_agent.dart';
import '../../../core/data/order_item_status.dart';
import '../../orders/presentation/order_presenter.dart';
import '../../orders/presentation/order_data_source.dart';
import '../../orders/presentation/orders_table_metrics.dart';
import '../../commands/data/command_repository.dart';
import '../../commands/presentation/commands_page.dart';
import '../../orders/presentation/order_cart_panel.dart';
import '../../orders/presentation/item_void_reason_dialog.dart';
import '../../orders/presentation/product_config_dialog.dart';
import '../../scale/presentation/scale_workstation_page.dart';
import '../../settings/presentation/api_url_settings_dialog.dart';
import '../../settings/presentation/terminal_preferences_dialog.dart';
import '../../scale/services/scale_window_launcher.dart';
import '../../../core/input/code_lookup_service.dart';
import '../../../core/input/pdv_input_router.dart';
import '../../../core/input/pdv_screen.dart';
import '../../../core/input/pdv_shortcuts.dart';
import 'pdv_help_dialog.dart';
import '../data/pdv_repository.dart';
import 'pdv_cloud_banner.dart';
import 'pdv_navigation_shell.dart';
import 'pdv_navigation_rail.dart';
import 'pdv_operational_chrome.dart';
import 'pdv_shortcut_bar.dart';
import '../../cash/domain/cash_session_label.dart';
import '../../cash/presentation/cash_auth_dialog.dart';
import 'pdv_cash_center_dialog.dart';
import 'pdv_presenter.dart';
import 'pdv_settings_menu_dialog.dart';
import 'orders_date_range_menu.dart';
import 'product_catalog_panel.dart';
import 'table_details_panel.dart';

import '../../orders/data/order_draft.dart';
import '../../orders/data/order_draft_cart.dart';
import '../../orders/data/order_draft_commands.dart';
import '../../orders/data/order_draft_materializer.dart';
import '../../orders/presentation/command_attach_dialog.dart';

part 'home_page_cash.dart';
part 'home_page_cash_ops.dart';
part 'home_page_cash_print.dart';
part 'home_page_commands.dart';
part 'home_page_commands_view.dart';
part 'home_page_customer.dart';
part 'home_page_kitchen.dart';
part 'home_page_draft.dart';
part 'home_page_draft_flow.dart';
part 'home_page_draft_items.dart';
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
part 'home_page_scan.dart';
part 'home_page_scan_actions.dart';

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
        _CashPrintSection,
        _CommandSection,
        _CommandView,
        _FiscalSection,
        _InputSection,
        _ScanSection,
        _ScanActionsSection,
        _CustomerSection,
        _DraftSection,
        _DraftFlowSection,
        _DraftCommandItemsSection,
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
  String flowStep = 'order';
  @override
  String? orderType = 'counter';
  @override
  String search = '';
  @override
  String? category;
  @override
  Map<String, dynamic>? cashSession;

  /// Id da sessão para a qual o saldo foi liberado nesta tela (§conferência
  /// às cegas). Guardar o id, e não um `bool`, faz a liberação esquecer
  /// sozinha quando o turno muda — sem isso, o saldo revelado num fechamento
  /// continuaria visível no caixa seguinte, aberto por outra pessoa.
  String? _cashBalanceRevealedForSessionId;
  /// O carrinho antes de o pedido existir. Vive e morre com esta tela: um
  /// rascunho abandonado não deixa rastro no servidor, que é justamente o
  /// ganho de adiar a criação.
  @override
  final OrderDraftCart draft = OrderDraftCart();
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
  final catalogSearchFocus = FocusNode(debugLabel: 'catalog-search');
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

  StreamSubscription<NetworkStatus>? syncStatusSubscription;
  StreamSubscription<void>? ordersSignalSubscription;
  StreamSubscription<String>? realtimeSignalSubscription;
  Timer? realtimeRefreshDebounce;
  final Set<String> pendingRealtimeTopics = {};
  bool realtimeRefreshRunning = false;
  bool realtimeRefreshQueued = false;

  /// O controlador central de entrada: teclado, leitor USB, leitor serial e
  /// área de transferência entram por aqui e saem como o MESMO evento.
  @override
  late final PdvInputRouter inputRouter;
  @override
  CodeLookupService? codeLookup;
  /// Os códigos lidos que pertencem à PÁGINA DAS COMANDAS.
  ///
  /// Ela é um widget próprio, com estado próprio, e o leitor é capturado aqui
  /// na casca — o teclado não tem dono quando nenhum campo está focado. Este
  /// canal é a ponte: sem ele, o operador teria de clicar no campo "Passe o
  /// cartão" antes de cada leitura, que é justamente o gesto que o leitor
  /// existe para eliminar.
  @override
  final StreamController<String> commandPageCodes =
      StreamController<String>.broadcast();
  StreamSubscription<ScannedCode>? codeSubscription;
  StreamSubscription<PdvShortcut>? shortcutSubscription;

  /// Enquanto o modal de configuração de produto está aberto, uma nova leitura
  /// do MESMO produto soma quantidade lá dentro em vez de abrir outro modal.
  @override
  StreamController<void>? productScanRepeats;
  @override
  String? scanningProductId;
  @override
  NetworkStatus networkStatus = const NetworkStatus(
    phase: NetworkPhase.unknown,
  );
  @override
  bool offlineMode = false;

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
    inputRouter = PdvInputRouter(readContext: _readInputContext);
    codeSubscription = inputRouter.codes.listen(_onCodeScanned);
    shortcutSubscription = inputRouter.shortcuts.listen(_onShortcut);
    HardwareKeyboard.instance.addHandler(inputRouter.handleKeyEvent);
    repository = PdvRepository(api: api, accessToken: token);
    presenter = PdvPresenter(repository);
    updateService = PdvUpdateService();
    unawaited(_checkPdvVersion());
    networkStatus = api.status;
    syncStatusSubscription = api.statusChanges.listen((status) {
      if (!mounted) return;
      final online = status.hasConnection;
      // A rede voltar é motivo para reler os dados, não para reconstruir a
      // tela. Como `_load` só apaga a tela na primeira carga, uma oscilação
      // agora passa despercebida pelo operador — antes ela devolvia o PDV a
      // uma tela em branco no meio do atendimento.
      final shouldRefresh = online && !loading && !refreshing && offlineMode;
      setState(() {
        networkStatus = status;
        offlineMode = !online;
      });
      if (online) widget.controller.markOnline();
      // Com a conexão de volta, o aviso de "sem conexão" perdeu o assunto e
      // sai sozinho — o operador não precisa fechá-lo à mão.
      if (online) ErrorCenterScope.read(context).dismissByKey('connectivity');
      if (shouldRefresh) unawaited(_load());
    });
    // Uma escrita deste terminal, ou um evento do servidor, mudou um pedido:
    // a tela relê. Sem cópia local, reler é uma ida à API — por isso o sinal
    // é debounced na origem, e não uma consulta por evento.
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
        if (topics.contains('cash_auth')) {
          await widget.controller.syncSupervisorPassword(
            restaurantId: restaurantId,
            force: true,
          );
        }

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

  /// A impressora caiu — registra, mas NÃO interrompe o operador.
  ///
  /// A disponibilidade é reavaliada de 15 em 15 segundos e a fila reimprime
  /// sozinha. Com uma impressora desligada, cada oscilação virava um aviso
  /// novo por cima da tela de venda: uma fila de Toasts que o operador não
  /// tinha como resolver no meio do atendimento, sobre algo que o sistema já
  /// está tentando resolver por conta própria.
  ///
  /// Silencioso não é ignorado. A causa vai para o log, o trabalho continua na
  /// fila com o estado dele, e a Fila de impressão (menu do PDV) mostra o que
  /// está pendente, o motivo e o botão de tentar agora.
  /// Liga o agente de impressão desta unidade.
  ///
  /// Sem token ou sem restaurante ele não tem o que consultar — acontece antes
  /// do bootstrap e depois de um logout. O próprio agente ignora chamadas
  /// repetidas com os mesmos dois valores, então chamar a cada carga é de
  /// graça.
  void _startPrintAgent() {
    final restaurant = selectedRestaurantId;
    if (token.isEmpty || restaurant == null || restaurant.isEmpty) {
      AppLogger.instance.info(
        'print_agent_aguarda',
        data: {'motivo': 'restaurante ou sessao ainda nao definidos'},
      );
      return;
    }
    deviceAgent.start(token: token, restaurantId: restaurant);
  }

  void _onPrinterStatusChanged() {
    final status = deviceAgent.printerAvailability.value;
    final disconnectedAfterUse =
        status.phase == PrinterAvailabilityPhase.unavailable &&
        lastPrinterPhase == PrinterAvailabilityPhase.available;
    lastPrinterPhase = status.phase;
    if (!disconnectedAfterUse) return;
    AppLogger.instance.warning(
      'impressora_indisponivel',
      data: {'motivo': status.message},
    );
  }

  /// Relê do servidor o que está na tela.
  ///
  /// Chamado quando algo mudou — uma escrita daqui, um evento do WebSocket.
  /// Como não há cópia local, reler é uma ida à API; por isso só a tela que
  /// está aberta é recarregada, e não tudo.
  Future<void> _refreshFromSignal() async {
    if (flowStep == 'orders') {
      await _reloadOrders();
      return;
    }
    final current = activeOrder;
    if (current == null || flowStep != 'order') return;
    await _refreshOrder();
  }

  @override
  Future<List<Map<String, dynamic>>> _list(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    return repository.list(path, query: query);
  }

  /// Por que este terminal não pode usar o caixa aberto (409/403 do servidor).
  ///
  /// Guardado em vez de descartado porque a mensagem já diz quem está com o
  /// caixa, de onde e desde quando — é o que o operador precisa para decidir
  /// entre esperar e pedir uma transferência gerencial.
  String? cashSessionBlockMessage;

  /// UUID desta instalação. Nasce na primeira abertura e não muda mais — é o
  /// que faz o backend reconhecer o caixa aberto aqui como sendo daqui.
  String get _terminalInstallationId =>
      widget.preferences.terminalInstallationId;

  /// Nome amigável do terminal. Um padrão derivado do UUID até a loja
  /// renomeá-lo (Configurações › Terminal) — melhor do que expor o UUID cru
  /// numa mensagem de bloqueio.
  String get _terminalName {
    final saved = widget.preferences.terminalName;
    if (saved.isNotEmpty) return saved;
    final nodeId = _terminalInstallationId;
    if (nodeId.isEmpty) return '';
    final suffix = nodeId.length <= 6 ? nodeId : nodeId.substring(0, 6);
    return 'Caixa $suffix';
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
      final bootstrap = await presenter.load(
        selectedRestaurantId: selectedRestaurantId,
        userRestaurantId: widget.controller.session!.user.restaurantId,
        userId: widget.controller.session!.user.id,
      );
      restaurants = bootstrap.restaurants;
      selectedRestaurantId = bootstrap.selectedRestaurantId;
      widget.controller.setActiveRestaurant(selectedRestaurantId);
      // Com a unidade resolvida, o agente assume a fila de impressão dela.
      //
      // É ele quem imprime o que o SERVIDOR cria: a comanda de cozinha, o
      // cupom de cancelamento, a nota de pesagem, o DANFE. Recibo e teste saem
      // por outro caminho, direto na impressora escolhida — por isso um agente
      // parado aparece para o operador exatamente como "só a comanda não sai,
      // e sem erro nenhum".
      //
      // Vários terminais da mesma unidade podem servir esta fila ao mesmo
      // tempo: cada trabalho é reservado no servidor antes de virar papel
      // (`/print-jobs/{id}/claim/`), e quem perde a corrida simplesmente
      // ignora aquele cupom.
      _startPrintAgent();
      await widget.controller.syncSupervisorPassword(
        restaurantId: selectedRestaurantId,
      );
      final catalog = bootstrap.catalog;
      stations = catalog.cashStations;
      products = catalog.products;
      categories = catalog.categories;
      tables = catalog.tables;
      commands = catalog.commands;
      paymentMethods = catalog.paymentMethods;
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
        if (cashSessionBlockMessage != null && mounted) {
          showAppToast(
            context,
            cashSessionBlockMessage!,
            title: 'Caixa indisponível neste terminal',
            // Bloqueia o recebimento: se ficasse só no sino, o operador
            // apertaria "receber" e a tela não reagiria.
            severity: AppErrorSeverity.failure,
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
        // Rascunho que sobrou de uma sessão anterior (app fechado com a
        // comanda aberta e vazia) não é venda: some antes de alguém o ver.
        unawaited(_sweepStaleDrafts());
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
    _leaveActiveOrder();
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
      orderType = 'counter';
      category = null;
      flowStep = 'order';
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
    if (flowStep == 'commands') return PdvDestination.commands;
    if (flowStep == 'orders') return PdvDestination.orders;
    if (flowStep == 'table_details' ||
        (flowStep == 'context' && orderType != 'command')) {
      return PdvDestination.tables;
    }
    return PdvDestination.sale;
  }

  @override
  Future<void> _navigateTo(PdvDestination destination) async {
    switch (destination) {
      case PdvDestination.sale:
        if (activeOrder != null) {
          setState(() => flowStep = 'order');
        } else {
          await _goHome();
        }
        return;
      case PdvDestination.tables:
        // Trocar de destino no trilho é sair desta venda. Com carrinho
        // montado, o operador confirma antes — o rascunho não sobrevive à
        // troca, e perdê-lo em silêncio por um toque no trilho seria digitar
        // tudo de novo com o cliente na frente.
        if (!await _confirmLeavingPendingItems()) return;
        _leaveActiveOrder();
        _discardDraft();
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
      case PdvDestination.commands:
        if (!await _confirmLeavingPendingItems()) return;
        _leaveActiveOrder();
        _discardDraft();
        setState(() {
          activeOrder = null;
          selectedCommand = null;
          orderItems = [];
          flowStep = 'commands';
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
      balanceVisible: _canSeeCashBalance,
    );
    if (!mounted || action == null) return;
    if (action == 'toggle_balance') {
      await _toggleCashBalanceVisibility();
      if (mounted) await _openCashCenter();
      return;
    }
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
        : await deviceAgent.printQueue.summary(scope: scope);
    if (!mounted) return;
    final selection = await PdvSettingsMenuDialog.show(
      context,
      canManageDevices: widget.controller.session!.user.canManageDevices,
      printQueueCount: printQueue?.total ?? 0,
      isDark: widget.isDark,
      isFullScreen: widget.isFullScreen,
    );
    if (!mounted || selection == null) return;
    if (selection == 'scale_workstation') await _openScaleWindow();
    if (selection == 'printer') _openDeviceSettings(DeviceKind.printer);
    if (selection == 'scale') _openDeviceSettings(DeviceKind.scale);
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
        // O nome do terminal viaja em TODA requisição. Sem reler aqui, a
        // renomeação só valeria na próxima abertura do PDV — e o operador que
        // acabou de batizar o caixa continuaria vendo o nome antigo na
        // mensagem de "caixa aberto em outra máquina".
        api.terminalLabel = _terminalName;
      }
    }
    if (selection == 'print_queue' && mounted) {
      await PrintQueueDialog.show(context, deviceAgent);
    }
    if (selection == 'api_url' && mounted) {
      final saved = await ApiUrlSettingsDialog.show(
        context,
        widget.preferences,
        widget.controller.apiBaseUrl,
      );
      if (!mounted || !saved) return;

      final config = await AppConfig.load(
        manualOverrideUrl: widget.preferences.apiBaseUrlOverride,
      );
      await widget.controller.updateApiBaseUrl(config.apiBaseUrl);
      // O token pertence ao servidor anterior. Encerrar a sessão força a
      // página a ser recriada no login e impede misturar dados dos backends.
      await widget.controller.logout();
      return;
    }
    if (selection == 'theme') widget.onToggleTheme();
    if (selection == 'fullscreen') widget.onToggleFullScreen();
    if (selection == 'logout') widget.controller.logout();
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
    final hasItems = orderItems.any(OrderItemStatus.countsTowardBill);
    return !hasItems && registeredPayments.isEmpty;
  }

  /// Descarta o pedido que foi aberto e não virou nada.
  ///
  /// O fluxo atual só cria ao incluir o primeiro item, mas pedidos vazios de
  /// versões anteriores ou retomados de outro terminal ainda podem existir.
  /// Eles prendem a comanda sem representar consumo; por isso o descarte não
  /// pede senha nem justificativa comercial.
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

  /// Sai do pedido ativo: se ele ficou vazio, descarta.
  ///
  /// TODA saída passa por aqui — voltar ao início, abrir a lista de Pedidos,
  /// ir para Mesas, trocar de restaurante, abrir outra comanda por cima. Só
  /// o `_goHome` descartava, e cada outra saída deixava um pedido vazio para
  /// trás: reabrir a mesma comanda criava mais um, e a tela de Pedidos
  /// enchia de `#LOCAL-…` com R$ 0,00 que ninguém abriu de propósito.
  ///
  /// O pedido é capturado ANTES do `setState` de quem chama (depois dele não
  /// há mais o que descartar) e o descarte segue em segundo plano: navegar
  /// não pode esperar a rede. [except] preserva o pedido que está sendo
  /// reaberto — retomar a própria comanda não é sair dela.
  @override
  void _leaveActiveOrder({String? except}) {
    final current = activeOrder;
    if (current == null || !_activeOrderIsEmpty) return;
    if (except != null && '${current['id']}' == except) return;
    unawaited(_discardEmptyOrder(current));
  }

  /// Apaga os rascunhos deste terminal que ficaram órfãos.
  ///
  /// Quem sai do pedido pela tela descarta na hora ([_leaveActiveOrder]);
  /// isto cobre o que não passou por lá — o app fechado com a comanda aberta
  /// e vazia. Um rascunho vazio não é venda e prende a mesa.
  @override
  Future<void> _sweepStaleDrafts() async {
    final restaurant = restaurantId;
    if (restaurant == null) return;
    try {
      final drafts = await _list(
        '/orders/',
        // `open`, e nao `draft`: esse status nunca existiu no backend, cujos
        // valores sao open/awaiting_payment/paid/cancelled/refunded. A
        // consulta voltava 400, o `catch` de baixo engolia, e esta varredura
        // passou a producao inteira sem apagar um unico rascunho orfao.
        query: {'restaurant': restaurant, 'status': 'open', 'page_size': 50},
      );
      final keep = '${activeOrder?['id'] ?? ''}';
      var removed = 0;
      for (final draft in drafts) {
        final id = '${draft['id'] ?? ''}';
        if (id.isEmpty || id == keep) continue;
        final items = draft['items'] as List? ?? const [];
        if (items.isNotEmpty) continue;
        try {
          await api.delete('/orders/$id/', accessToken: token);
          removed += 1;
        } catch (_) {
          // Um rascunho que o servidor recusa apagar (já virou venda, ou
          // outro caixa o assumiu) não é problema desta varredura.
        }
      }
      if (removed > 0) {
        AppLogger.instance.info(
          'rascunhos_orfaos_descartados',
          data: {'quantidade': removed},
        );
      }
    } catch (erro) {
      // Limpeza de fundo: falhar aqui não pode atrapalhar a venda em curso —
      // mas tem de APARECER. Engolir em silêncio foi o que manteve a consulta
      // quebrada indefinidamente, com o servidor recusando toda varredura e
      // ninguém sabendo.
      AppLogger.instance.warning(
        'rascunhos_orfaos_varredura_falhou',
        data: {'erro': '$erro'},
      );
    }
  }

  @override
  /// Volta para o começo de um atendimento novo: catálogo à esquerda,
  /// carrinho vazio à direita.
  ///
  /// Antes isto caía numa tela de "escolha o tipo de atendimento". Ela custava
  /// um gesto a cada venda para responder o que é quase sempre balcão, e a
  /// opção "comanda" abria o cartão de verdade ali mesmo. Agora o destino já
  /// nasce escolhido e trocá-lo é a barra no topo do carrinho — sem nada no
  /// servidor até o pedido precisar existir.
  Future<void> _goHome() async {
    _leaveActiveOrder();
    _discardDraft();
    setState(() {
      activeOrder = null;
      selectedTable = null;
      selectedCommand = null;
      selectedCustomer = null;
      orderItems = [];
      registeredPayments = [];
      orderType = 'counter';
      flowStep = 'order';
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
      setState(() {
        orderType = 'counter';
        flowStep = 'order';
      });
    } else if (flowStep == 'order' && activeOrder == null) {
      if (orderType == 'command') {
        setState(() => flowStep = 'context');
      } else {
        unawaited(_goHome());
      }
    } else if (activeOrder != null) {
      _goHome();
    }
  }

  @override
  void dispose() {
    deviceAgent.printerAvailability.removeListener(_onPrinterStatusChanged);
    deviceAgent.dispose();
    ordersSignalSubscription?.cancel();
    realtimeSignalSubscription?.cancel();
    realtimeRefreshDebounce?.cancel();
    pendingRealtimeTopics.clear();
    syncStatusSubscription?.cancel();
    HardwareKeyboard.instance.removeHandler(inputRouter.handleKeyEvent);
    codeSubscription?.cancel();
    commandPageCodes.close();
    shortcutSubscription?.cancel();
    productScanRepeats?.close();
    inputRouter.dispose();
    paymentReference.dispose();
    paymentAmount.dispose();
    ordersSearchDebounce?.cancel();
    ordersSearchController.dispose();
    ordersSearchFocus.dispose();
    commandSearchFocus.dispose();
    catalogSearchFocus.dispose();
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
          // O cupom não saiu. Aviso iria só para o sino e o operador
          // entregaria a venda sem papel sem perceber.
          severity: AppErrorSeverity.failure,
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
  /// Quem confere a senha é o servidor — é ele que guarda o hash e registra a
  /// autorização na auditoria.
  @override
  // Consumido pelas seções de caixa via declaração abstrata.
  Future<Map<String, dynamic>> _approveWithCashPassword({
    required String reason,
    required String password,
    // Com `movementId`, autoriza UMA sangria/suprimento pendente; sem ele,
    // a divergência da própria sessão. É o mesmo endpoint nos dois casos.
    String? movementId,
  }) async {
    final sessionId = '${cashSession!['id']}';
    final alvo = movementId == null || movementId.isEmpty
        ? const <String, dynamic>{}
        : {'movement': movementId};

    return api.post(
      '/cash-register/$sessionId/approve/',
      body: {'reason': reason, 'cash_password': password, ...alvo},
      accessToken: token,
    );
  }
}
