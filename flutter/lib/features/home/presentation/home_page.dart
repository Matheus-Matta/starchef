import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/errors/app_error.dart';
import '../../../core/errors/app_error_host.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/formatters/value_formatters.dart';
import '../../../core/storage/local_preferences.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../devices/presentation/device_list_page.dart';
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
import '../../topology/domain/local_topology_config.dart';
import '../../topology/presentation/local_topology_dialog.dart';
import '../../topology/services/local_topology_service.dart';
import '../data/pdv_repository.dart';
import 'pdv_navigation_shell.dart';
import 'pdv_presenter.dart';
import 'product_catalog_panel.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.controller,
    required this.isDark,
    required this.onToggleTheme,
    required this.isFullScreen,
    required this.onToggleFullScreen,
    required this.preferences,
  });

  final AuthController controller;
  final bool isDark;
  final VoidCallback onToggleTheme;
  final bool isFullScreen;
  final VoidCallback onToggleFullScreen;
  final LocalPreferences preferences;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  ApiClient get api => widget.controller.repository.apiClient;
  String get token => widget.controller.session!.accessToken;
  String? get restaurantId => selectedRestaurantId;

  bool loading = true;

  /// Recarga em segundo plano: os dados estão sendo atualizados, mas a tela
  /// atual continua utilizável.
  bool refreshing = false;
  bool busy = false;
  bool printingReceipt = false;
  bool emittingInvoice = false;
  bool divergenceDialogOpen = false;
  bool movementApprovalDialogOpen = false;
  String flowStep = 'type';
  String? orderType;
  String search = '';
  String? category;
  Map<String, dynamic>? cashSession;

  /// A sessão de caixa veio do cache local, não de uma leitura ao servidor.
  /// O estado pode ter mudado em outro terminal enquanto este esteve offline.
  bool cashSessionFromCache = false;
  Map<String, dynamic>? activeOrder;
  Map<String, dynamic>? selectedTable;
  Map<String, dynamic>? selectedCommand;
  String commandSearch = '';
  Map<String, dynamic>? selectedCustomer;
  Map<String, dynamic>? pendingCashMovement;
  List<Map<String, dynamic>> stations = [];
  List<Map<String, dynamic>> restaurants = [];
  List<Map<String, dynamic>> products = [];
  List<Map<String, dynamic>> categories = [];
  List<Map<String, dynamic>> tables = [];
  List<Map<String, dynamic>> commands = [];
  List<Map<String, dynamic>> orderItems = [];
  List<Map<String, dynamic>> paymentMethods = [];
  List<Map<String, dynamic>> registeredPayments = [];
  List<Map<String, dynamic>> orders = [];
  bool ordersLoading = false;
  String? loadErrorMessage;
  String orderStatusFilter = 'pending';
  String orderSearch = '';
  String? orderTypeFilter;
  String orderOrdering = '-opened_at';
  DateTimeRange? orderDateRange;

  /// A busca não alcançou o servidor e o resultado saiu do que já estava
  /// guardado — pode faltar pedido antigo. A tela avisa em vez de fingir que
  /// achou tudo.
  bool ordersPartial = false;
  final ordersSearchController = TextEditingController();
  Timer? ordersSearchDebounce;
  String? selectedPaymentMethod;
  String paymentDigits = '0';
  String? removingPaymentId;
  final paymentReference = TextEditingController();
  final paymentAmount = TextEditingController();
  String? selectedRestaurantId;
  late final LocalDeviceAgent deviceAgent;
  late final PdvRepository repository;
  late final PdvPresenter presenter;

  /// Cópia local dos pedidos, com as edições offline já aplicadas.
  final LocalOrderStore orderStore = LocalOrderStore();
  StreamSubscription<NetworkSyncStatus>? syncStatusSubscription;
  StreamSubscription<void>? ordersSignalSubscription;
  LocalTopologyService? topologyService;
  NetworkSyncStatus networkStatus = const NetworkSyncStatus(
    phase: NetworkSyncPhase.unknown,
  );
  bool offlineMode = false;

  /// Este terminal é um Caixa Cliente, que depende do principal para gravar.
  bool get isSecondaryStation =>
      topologyService?.config?.mode == LocalTopologyMode.client;

  /// O principal respondeu ao último teste de conexão.
  bool get principalReachable =>
      topologyService?.status.phase == LocalTopologyPhase.clientReady;
  int offlinePendingCount = 0;
  bool sidebarExpanded = true;

  List<Map<String, dynamic>> get visibleProducts => products.where((product) {
    final matchesCategory =
        category == null || '${product['category']}' == category;
    final term = search.trim().toLowerCase();
    return matchesCategory &&
        (term.isEmpty ||
            '${product['name']}'.toLowerCase().contains(term) ||
            '${product['internal_code'] ?? ''}'.toLowerCase().contains(term) ||
            '${product['category_name'] ?? ''}'.toLowerCase().contains(term));
  }).toList();

  double get paidTotal => registeredPayments.fold(
    0,
    (total, payment) => total + _number(payment['amount']),
  );
  double get remainingTotal =>
      (_number(activeOrder?['total']) - paidTotal).clamp(0, double.infinity);
  double get changeTotal => registeredPayments.fold(
    0,
    (total, payment) => total + _number(payment['change_amount']),
  );
  double get receivedTotal => registeredPayments.fold(
    0,
    (total, payment) =>
        total + _number(payment['amount']) + _number(payment['change_amount']),
  );
  double get paymentValue => (int.tryParse(paymentDigits) ?? 0) / 100;
  Map<String, dynamic>? get selectedMethod =>
      paymentMethods.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == selectedPaymentMethod,
        orElse: () => null,
      );
  bool get selectedMethodIsCash => selectedMethod?['method_type'] == 'cash';
  double get pendingChange =>
      selectedMethodIsCash && paymentValue > remainingTotal
      ? paymentValue - remainingTotal
      : 0;
  bool get hasCashDivergence =>
      cashSession?['status'] == 'pending_manager_approval';
  double get cashBalance {
    if (cashSession?['current_balance'] != null) {
      return _number(cashSession!['current_balance']);
    }
    return (cashSession?['movements'] as List? ?? const [])
        .cast<Map<String, dynamic>>()
        .where((movement) => movement['status'] == 'approved')
        .fold(0, (total, movement) => total + _number(movement['amount']));
  }

  @override
  void initState() {
    super.initState();
    deviceAgent = LocalDeviceAgent(api: api);
    repository = PdvRepository(api: api, accessToken: token);
    presenter = PdvPresenter(repository);
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
    _load();
  }

  /// Relê o que está na tela a partir da cópia local.
  Future<void> _refreshFromSignal() async {
    final scope = api.sessionScope;
    if (scope == null) return;
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

  Future<List<Map<String, dynamic>>> _list(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    return repository.list(path, query: query);
  }

  Future<void> _ensureTopology() async {
    final selected = restaurantId;
    final accountId = widget.controller.session!.user.accountId;
    if (selected == null || accountId == null || accountId.trim().isEmpty) {
      return;
    }
    final existing = topologyService;
    if (existing != null) {
      existing.updateRestaurant(selected);
      return;
    }
    final service = LocalTopologyService(
      api: api,
      accessToken: token,
      accountId: accountId,
      actorId: widget.controller.session!.user.id,
      restaurantId: selected,
    );
    try {
      await service.start();
      if (!mounted) {
        await service.shutdown();
        return;
      }
      topologyService = service;
      service.addListener(_onTopologyChanged);
      _onTopologyChanged();
    } catch (_) {
      await service.shutdown();
      rethrow;
    }
  }

  void _onTopologyChanged() {
    final service = topologyService;
    if (service == null || !mounted) return;
    final config = service.config;
    if (service.status.phase == LocalTopologyPhase.starting ||
        config == null ||
        config.mode == LocalTopologyMode.client) {
      deviceAgent.stop();
    } else if (restaurantId != null) {
      deviceAgent.start(token: token, restaurantId: restaurantId!);
    }
    setState(() {});
  }

  /// Recarrega os dados do PDV.
  ///
  /// A tela só é apagada na primeira vez, quando ainda não há nada para
  /// mostrar. Depois disso a recarga acontece por baixo: os dados são
  /// trocados quando chegam e o operador continua na mesma tela, com o mesmo
  /// pedido aberto. Antes, qualquer oscilação de rede — cair e voltar —
  /// devolvia o PDV a uma tela em branco no meio do atendimento.
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
      );
      restaurants = bootstrap.restaurants;
      selectedRestaurantId = bootstrap.selectedRestaurantId;
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
      try {
        await _ensureTopology();
      } catch (error) {
        if (mounted) {
          showAppToast(
            context,
            'A rede local não iniciou: $error',
            title: 'Rede local indisponível',
            severity: AppErrorSeverity.warning,
            autoDismissAfter: const Duration(seconds: 8),
          );
        }
      }
      try {
        final currentSession = await api.get(
          '/cash-register/current/',
          accessToken: token,
        );
        final stationIds = stations.map((item) => '${item['id']}').toSet();
        cashSession = stationIds.contains('${currentSession['cash_station']}')
            ? currentSession
            : null;
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
        cashSessionFromCache = currentSession['_offline_cache'] == true;
      } on ApiException catch (error) {
        // 404 significa "nenhum caixa aberto". Sem rede e sem cache prévio o
        // terminal também não sabe o estado do caixa; em ambos os casos ele
        // segue carregando, porque abrir/fechar já exige servidor e falharia
        // com mensagem própria.
        if (error.statusCode != null && error.statusCode != 404) rethrow;
        cashSession = null;
        pendingCashMovement = null;
        cashSessionFromCache = false;
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
        if (restaurantId != null &&
            topologyService?.config?.mode != LocalTopologyMode.client) {
          deviceAgent.start(token: token, restaurantId: restaurantId!);
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
      );
      if (!mounted) return;
      if (opened) {
        showAppToast(context, 'Balança Rápida aberta em uma janela independente.');
        return;
      }
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

  /// Página de pedidos guardada localmente.
  ///
  /// A listagem já vem com os itens de cada pedido, então uma página é a
  /// cópia completa do que dá para editar offline. 50 é um meio-termo: cobre
  /// o movimento recente sem transferir centenas de pedidos com todos os
  /// itens aninhados a cada abertura do PDV.
  static const _ordersPageSize = 50;

  /// Consulta fixa de aquecimento do cache.
  ///
  /// Não leva filtro nenhum de propósito: o cache do `ApiClient` é gravado por
  /// consulta exata, então esta precisa ser sempre a mesma para que exista uma
  /// lista guardada quando a rede cair. Os filtros da tela usam
  /// [_ordersServerQuery], que é outra consulta.
  Map<String, dynamic> get _ordersQuery => {
    'page_size': _ordersPageSize,
    'ordering': '-opened_at',
    'restaurant': restaurantId,
  };

  /// Consulta da tela de Pedidos, com os filtros do operador.
  ///
  /// Manda para a API o que ela sabe filtrar (busca, tipo, período,
  /// ordenação), para que a procura alcance o histórico inteiro e não só a
  /// página que já foi baixada. O agrupamento de situação continua sendo
  /// refinado na memória por [_matchesStatusFilter] — "pendentes" cruza
  /// `status` e `payment_status`, o que a API não expressa num parâmetro só.
  Map<String, dynamic> get _ordersServerQuery {
    final query = <String, dynamic>{
      'page_size': _ordersPageSize,
      'ordering': orderOrdering,
      'restaurant': restaurantId,
    };
    final term = orderSearch.trim();
    if (term.isNotEmpty) query['search'] = term;
    if (orderTypeFilter != null) query['order_type'] = orderTypeFilter;
    if (orderStatusFilter == 'pending') {
      query['payment_status'] = 'pending';
    } else if (orderStatusFilter != 'all') {
      query['status'] = orderStatusFilter;
    }
    final range = orderDateRange;
    if (range != null) {
      query['opened_after'] = _isoDate(range.start);
      query['opened_before'] = _isoDate(range.end);
    }
    return query;
  }

  static String _isoDate(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  /// Agrupamento de situação escolhido no seletor da tela.
  bool _matchesStatusFilter(Map<String, dynamic> order) {
    switch (orderStatusFilter) {
      case 'all':
        return true;
      case 'pending':
        return order['payment_status'] != 'paid' &&
            {'open', 'awaiting_payment'}.contains('${order['status']}');
      default:
        return '${order['status']}' == orderStatusFilter;
    }
  }

  /// Filtro local, usado quando a busca não alcançou o servidor.
  bool _matchesLocalFilters(Map<String, dynamic> order) {
    if (!_matchesStatusFilter(order)) return false;
    if (orderTypeFilter != null &&
        '${order['order_type']}' != orderTypeFilter) {
      return false;
    }
    final range = orderDateRange;
    if (range != null) {
      final openedAt = DateTime.tryParse('${order['opened_at'] ?? ''}');
      if (openedAt == null) return false;
      final day = DateTime(openedAt.year, openedAt.month, openedAt.day);
      final start = DateTime(
        range.start.year,
        range.start.month,
        range.start.day,
      );
      final end = DateTime(range.end.year, range.end.month, range.end.day);
      if (day.isBefore(start) || day.isAfter(end)) return false;
    }
    final term = orderSearch.trim().toLowerCase();
    if (term.isEmpty) return true;
    final haystack =
        '${order['sequence'] ?? ''} ${order['customer_name'] ?? ''} '
                '${order['table_number'] ?? ''} ${order['command_code'] ?? ''}'
            .toLowerCase();
    return haystack.contains(term);
  }

  /// Ordena a lista local pelo mesmo critério pedido ao servidor.
  List<Map<String, dynamic>> _sortedLocally(List<Map<String, dynamic>> list) {
    final descending = orderOrdering.startsWith('-');
    final field = descending ? orderOrdering.substring(1) : orderOrdering;
    final sorted = [...list];
    sorted.sort((a, b) {
      final comparison = switch (field) {
        'total' => _number(a['total']).compareTo(_number(b['total'])),
        'sequence' => _number(a['sequence']).compareTo(_number(b['sequence'])),
        _ => '${a['opened_at'] ?? ''}'.compareTo('${b['opened_at'] ?? ''}'),
      };
      return descending ? -comparison : comparison;
    });
    return sorted;
  }

  /// Baixa e guarda os pedidos recentes sem prender a interface.
  Future<void> _warmOrdersCache() async {
    if (restaurantId == null) return;
    try {
      await api.get('/orders/', query: _ordersQuery, accessToken: token);
    } catch (_) {
      // É só aquecimento de cache: sem rede, o que já estiver guardado serve,
      // e a tela de Pedidos reporta o problema quando for aberta.
    }
  }

  Future<void> _openOrders() async {
    final scope = api.sessionScope;
    // Abre já com o que está guardado: a lista aparece na hora e a versão do
    // servidor entra por cima quando chegar. Só mostra "carregando" quem
    // ainda não tem nada para ver.
    final cached = scope == null ? const <Map<String, dynamic>>[] : null;
    final local = cached ?? await _ordersFromStore(scope!);
    if (!mounted) return;
    setState(() {
      flowStep = 'orders';
      activeOrder = null;
      if (local.isNotEmpty) orders = _localResults(local);
      ordersLoading = orders.isEmpty;
    });
    await _reloadOrders();
  }

  /// Busca a lista com os filtros atuais, caindo para o cache quando sem rede.
  Future<void> _reloadOrders() async {
    final scope = api.sessionScope;
    try {
      final loaded = await _list('/orders/', query: _ordersServerQuery);
      final ofRestaurant = loaded
          .where((item) => '${item['restaurant']}' == restaurantId)
          .toList();
      if (scope != null) {
        await orderStore.saveAllFromServer(ofRestaurant, scope: scope);
        // A ordem e a seleção vêm do servidor, mas cada pedido é relido do
        // store para não apagar da tela uma edição feita offline que ainda
        // não subiu. Reler a lista inteira do store desfaria o filtro.
        final merged = <Map<String, dynamic>>[];
        for (final order in ofRestaurant) {
          final stored = await orderStore.read('${order['id']}', scope: scope);
          merged.add(stored ?? order);
        }
        orders = merged.where(_matchesStatusFilter).toList();
      } else {
        orders = ofRestaurant.where(_matchesStatusFilter).toList();
      }
      ordersPartial = false;
    } catch (error) {
      // Sem rede a busca vale só para o que já está guardado. A lista continua
      // útil — o operador precisa achar o pedido aberto agora —, mas a tela
      // avisa que o resultado pode estar incompleto.
      final localCopy = scope == null
          ? const <Map<String, dynamic>>[]
          : await _ordersFromStore(scope);
      if (localCopy.isNotEmpty) {
        orders = _localResults(localCopy);
        ordersPartial = true;
      } else if (mounted) {
        orders = [];
        ordersPartial = false;
        _error(error);
      }
    } finally {
      if (mounted) setState(() => ordersLoading = false);
    }
  }

  List<Map<String, dynamic>> _localResults(List<Map<String, dynamic>> source) =>
      _sortedLocally(source.where(_matchesLocalFilters).toList());

  /// Reaplica os filtros. A busca por texto espera o operador parar de digitar
  /// para não disparar uma requisição por tecla.
  void _onOrdersFilterChanged({bool debounce = false}) {
    ordersSearchDebounce?.cancel();
    if (!debounce) {
      setState(() => ordersLoading = orders.isEmpty);
      unawaited(_reloadOrders());
      return;
    }
    ordersSearchDebounce = Timer(
      const Duration(milliseconds: 400),
      () => unawaited(_reloadOrders()),
    );
  }

  Future<List<Map<String, dynamic>>> _ordersFromStore(String scope) async {
    final stored = await orderStore.recent(
      scope: scope,
      limit: _ordersPageSize,
    );
    return stored
        .where((item) => '${item['restaurant']}' == restaurantId)
        .toList();
  }

  /// Carrega o pedido para edição/pagamento, com o que houver disponível.
  ///
  /// A listagem já traz o pedido completo — o serializer aninha os itens —,
  /// então [fromList] é uma cópia legítima do detalhe, e não um resumo. Sem
  /// rede, ela é a fonte: antes o operador não conseguia abrir um pedido que
  /// não tivesse sido feito neste terminal, porque só a rota de detalhe tinha
  /// sido cacheada e ela nunca fora chamada para aquele pedido.
  Future<Map<String, dynamic>?> _orderDetail(
    Map<String, dynamic> fromList,
  ) async {
    final id = '${fromList['id'] ?? ''}';
    final scope = api.sessionScope;

    // Um pedido criado offline só existe localmente; buscá-lo no servidor
    // devolveria 404.
    if (id.startsWith('offline-') && scope != null) {
      final local = await orderStore.read(id, scope: scope);
      if (local != null) return local;
    }

    try {
      final fresh = await api.get('/orders/$id/', accessToken: token);
      if (scope != null) {
        // Guardar aqui preserva os itens lançados offline que o servidor
        // ainda não conhece.
        return await orderStore.saveFromServer(fresh, scope: scope);
      }
      return fresh;
    } on ApiException catch (error) {
      if (!error.isConnectivity) {
        if (mounted) _error(error);
        return null;
      }
      // A cópia local vem antes da entrada da listagem porque é ela que tem
      // as edições feitas sem rede.
      final local = scope == null
          ? null
          : await orderStore.read(id, scope: scope);
      final fallback = local ?? (fromList['items'] is List ? fromList : null);
      if (fallback != null) {
        if (mounted) _warnLocalOrderData();
        return fallback;
      }
      if (mounted) {
        _error(
          error,
          title: 'Este pedido ainda não está salvo neste terminal',
          action:
              'Abra a tela de Pedidos com a rede disponível ao menos uma vez '
              'para guardar os dados; depois ele funciona offline.',
        );
      }
      return null;
    } catch (error) {
      if (mounted) _error(error);
      return null;
    }
  }

  /// Avisa que a edição está usando a cópia local, uma vez por queda de rede.
  void _warnLocalOrderData() {
    ErrorCenterScope.read(context).report(
      AppError(
        title: 'Editando com os dados salvos localmente',
        message:
            'Sem conexão, este pedido é aberto a partir da última cópia '
            'guardada neste terminal. Se ele foi alterado em outro caixa, '
            'essas mudanças ainda não aparecem aqui.',
        origin: AppErrorOrigin.network,
        severity: AppErrorSeverity.warning,
        recommendedAction:
            'As alterações feitas agora entram na fila e sobem quando a rede '
            'voltar.',
        dedupeKey: 'order-local-copy',
      ),
    );
  }

  Future<void> _editOrder(Map<String, dynamic> order) async {
    final detail = await _orderDetail(order);
    if (detail == null) return;
    activeOrder = detail;
    orderType = '${detail['order_type']}';
    selectedTable = detail['table'] == null
        ? null
        : tables.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '${detail['table']}',
            orElse: () => null,
          );
    selectedCommand = detail['command'] == null
        ? null
        : commands.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '${detail['command']}',
            orElse: () => null,
          );
    selectedCustomer = detail['customer'] == null
        ? null
        : {
            'id': detail['customer'],
            'name': detail['customer_name'] ?? 'Cliente',
            'phone': '',
          };
    await _refreshOrder();
    if (mounted) setState(() => flowStep = 'order');
  }

  Future<void> _payOrder(Map<String, dynamic> order) async {
    final detail = await _orderDetail(order);
    if (detail == null) return;
    activeOrder = detail;
    orderType = '${detail['order_type']}';
    await _paymentDialog();
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
        ),
      ),
    );
  }

  PdvDestination get _selectedDestination {
    if (flowStep == 'scale-workstation') return PdvDestination.scale;
    if (flowStep == 'orders') return PdvDestination.orders;
    if (flowStep == 'context' || orderType == 'table') {
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
          orderType = 'table';
          flowStep = 'context';
        });
        return;
      case PdvDestination.orders:
        await _openOrders();
        return;
      case PdvDestination.finance:
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
    final action = await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        final scheme = Theme.of(dialogContext).colorScheme;
        return AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.account_balance_wallet_outlined),
              SizedBox(width: 10),
              Text('Financeiro do caixa'),
            ],
          ),
          content: SizedBox(
            width: 480,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(18),
                  decoration: BoxDecoration(
                    color: scheme.surfaceContainer,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        cashSession == null ? 'Caixa fechado' : 'Caixa aberto',
                        style: TextStyle(
                          color: cashSession == null
                              ? scheme.error
                              : const Color(0xFF167A3E),
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        cashSession == null
                            ? 'Abra uma sessão para iniciar as vendas.'
                            : _money(cashBalance),
                        style: TextStyle(
                          fontSize: cashSession == null ? 16 : 30,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      if (cashSession != null)
                        Text(
                          '${cashSession!['station'] ?? 'Estação atual'}',
                          style: TextStyle(color: scheme.onSurfaceVariant),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                if (cashSession == null)
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton.icon(
                      onPressed: () => Navigator.pop(dialogContext, 'open'),
                      icon: const Icon(Icons.lock_open),
                      label: const Text('Abrir caixa'),
                    ),
                  )
                else
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () =>
                              Navigator.pop(dialogContext, 'supply'),
                          icon: const Icon(Icons.add_circle_outline),
                          label: const Text('Suprimento'),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: () =>
                              Navigator.pop(dialogContext, 'withdrawal'),
                          icon: const Icon(Icons.remove_circle_outline),
                          label: const Text('Sangria'),
                        ),
                      ),
                    ],
                  ),
              ],
            ),
          ),
          actions: [
            if (cashSession != null)
              TextButton.icon(
                onPressed: () => Navigator.pop(dialogContext, 'close'),
                icon: const Icon(Icons.lock_outline),
                label: const Text('Fechar caixa'),
              ),
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Voltar'),
            ),
          ],
        );
      },
    );
    if (!mounted || action == null) return;
    if (action == 'open') await _openCash();
    if (action == 'supply' || action == 'withdrawal') {
      await _cashMovement(action);
    }
    if (action == 'close') await _closeCash();
  }

  Future<void> _openSettingsCenter() async {
    final selection = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        scrollable: true,
        title: const Row(
          children: [
            Icon(Icons.settings_outlined),
            SizedBox(width: 10),
            Text('Configurações do PDV'),
          ],
        ),
        content: SizedBox(
          width: 460,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.controller.session!.user.canManageDevices) ...[
                ListTile(
                  leading: const Icon(Icons.print_outlined),
                  title: const Text('Impressoras'),
                  subtitle: const Text('Conexão, driver e testes de impressão'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.pop(dialogContext, 'printer'),
                ),
                ListTile(
                  leading: const Icon(Icons.scale_outlined),
                  title: const Text('Balanças'),
                  subtitle: const Text(
                    'Porta, protocolo e impressora vinculada',
                  ),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.pop(dialogContext, 'scale'),
                ),
                const Divider(),
              ],
              ListTile(
                leading: const Icon(Icons.hub_outlined),
                title: const Text('Rede local de caixas'),
                subtitle: Text(
                  topologyService?.status.message ??
                      'Entre novamente para habilitar a identidade deste caixa.',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pop(dialogContext, 'topology'),
              ),
              ListTile(
                leading: const Icon(Icons.tune),
                title: const Text('Preferências deste terminal'),
                subtitle: const Text(
                  'Tempo da comanda, estabilidade, alertas e impressão',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pop(dialogContext, 'preferences'),
              ),
              ListTile(
                leading: const Icon(Icons.sync_problem_outlined),
                title: const Text('Operações pendentes'),
                subtitle: Text(
                  offlinePendingCount == 0
                      ? 'Nada aguardando o servidor'
                      : '$offlinePendingCount aguardando o servidor',
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.pop(dialogContext, 'outbox'),
              ),
              const Divider(),
              SwitchListTile(
                secondary: Icon(
                  widget.isDark
                      ? Icons.dark_mode_outlined
                      : Icons.light_mode_outlined,
                ),
                title: const Text('Tema escuro'),
                subtitle: const Text('Ajuste visual desta estação'),
                value: widget.isDark,
                onChanged: (_) {
                  Navigator.pop(dialogContext, 'theme');
                },
              ),
              ListTile(
                leading: Icon(
                  widget.isFullScreen
                      ? Icons.fullscreen_exit
                      : Icons.fullscreen,
                ),
                title: Text(
                  widget.isFullScreen
                      ? 'Sair da tela cheia'
                      : 'Usar tela cheia',
                ),
                subtitle: const Text('Atalho: F11'),
                onTap: () => Navigator.pop(dialogContext, 'fullscreen'),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Fechar'),
          ),
        ],
      ),
    );
    if (!mounted || selection == null) return;
    if (selection == 'printer') _openDeviceSettings(DeviceKind.printer);
    if (selection == 'scale') _openDeviceSettings(DeviceKind.scale);
    if (selection == 'topology') await _openTopologySettings();
    if (selection == 'preferences' && mounted) {
      await TerminalPreferencesDialog.show(context, widget.preferences);
    }
    if (selection == 'outbox' && mounted) await _openOutboxReview();
    if (selection == 'theme') widget.onToggleTheme();
    if (selection == 'fullscreen') widget.onToggleFullScreen();
  }

  Future<void> _openTopologySettings() async {
    final service = topologyService;
    final current = service?.config;
    if (service == null || current == null) {
      showAppToast(
        context,
        'A sessão restaurada não contém a identidade da conta. '
        'Saia e entre novamente antes de configurar a rede local.',
        title: 'Sessão incompleta',
        severity: AppErrorSeverity.warning,
        autoDismissAfter: const Duration(seconds: 6),
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
      _onTopologyChanged();
      final degraded =
          candidate.mode == LocalTopologyMode.client && !service.status.ready;
      showAppToast(
        context,
        degraded
            ? 'Modo Cliente salvo, mas o Caixa Principal está indisponível.'
            : candidate.mode == LocalTopologyMode.client
            ? 'Modo Cliente salvo. O agente físico local foi pausado.'
            : 'Configuração da rede local aplicada.',
        title: 'Rede local',
        severity: degraded ? AppErrorSeverity.warning : AppErrorSeverity.info,
        autoDismissAfter: degraded
            ? const Duration(seconds: 6)
            : const Duration(milliseconds: 2200),
      );
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
  Future<void> _goHome() async {
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

  Future<void> _showCashDivergence() async {
    if (!mounted || !hasCashDivergence || divergenceDialogOpen) return;
    divergenceDialogOpen = true;
    final username = TextEditingController();
    final password = TextEditingController();
    final cashPassword = TextEditingController();
    final reason = TextEditingController();
    final formKey = GlobalKey<FormState>();
    var authorizing = false;
    // Modo de autorização: false = login de gerente (online) / true = senha do
    // caixa do restaurante (verificável offline).
    var cashMode = false;
    try {
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => PopScope(
          canPop: false,
          child: StatefulBuilder(
            builder: (context, update) => AlertDialog(
              title: const Row(
                children: [
                  Icon(Icons.warning_amber_rounded, color: Colors.orange),
                  SizedBox(width: 10),
                  Expanded(child: Text('Divergência no caixa')),
                ],
              ),
              content: SizedBox(
                width: 520,
                child: Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'O PDV permanecerá bloqueado até que um gerente autorizado resolva o fechamento.',
                        ),
                        const SizedBox(height: 18),
                        _divergenceValue(
                          'Valor esperado',
                          _money(cashSession?['expected_amount']),
                        ),
                        _divergenceValue(
                          'Valor contado',
                          _money(cashSession?['actual_amount']),
                        ),
                        _divergenceValue(
                          'Diferença',
                          _differenceText(cashSession?['difference_amount']),
                          emphasized: true,
                        ),
                        if ('${cashSession?['notes'] ?? ''}'
                            .trim()
                            .isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text('Observação: ${cashSession!['notes']}'),
                        ],
                        const Divider(height: 32),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton.icon(
                            onPressed: authorizing
                                ? null
                                : () => update(() => cashMode = !cashMode),
                            icon: Icon(
                              cashMode
                                  ? Icons.person_outline
                                  : Icons.password_outlined,
                            ),
                            label: Text(
                              cashMode
                                  ? 'Usar login de gerente'
                                  : 'Usar senha do caixa',
                            ),
                          ),
                        ),
                        const SizedBox(height: 6),
                        if (!cashMode) ...[
                          TextFormField(
                            controller: username,
                            autofocus: true,
                            decoration: const InputDecoration(
                              labelText: 'Usuário autorizador',
                              helperText:
                                  'Gerente, administrador ou proprietário.',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                            validator: (value) =>
                                value == null || value.trim().isEmpty
                                ? 'Informe o usuário autorizador.'
                                : null,
                          ),
                          const SizedBox(height: 14),
                          TextFormField(
                            controller: password,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Senha',
                              helperText:
                                  'A credencial será descartada após a autorização.',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Informe a senha.'
                                : null,
                          ),
                        ] else ...[
                          TextFormField(
                            controller: cashPassword,
                            autofocus: true,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Senha do caixa',
                              helperText:
                                  'Senha de ações do caixa definida no restaurante — dispensa login de gerente.',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Informe a senha do caixa.'
                                : null,
                          ),
                        ],
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: reason,
                          maxLines: 3,
                          decoration: const InputDecoration(
                            labelText: 'Justificativa gerencial',
                            helperText:
                                'Explique por que a divergência está sendo aprovada.',
                          ),
                          validator: (value) =>
                              value == null || value.trim().isEmpty
                              ? 'Informe a justificativa.'
                              : null,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              actions: [
                TextButton.icon(
                  onPressed: authorizing
                      ? null
                      : () async {
                          Navigator.pop(dialogContext);
                          await widget.controller.logout();
                        },
                  icon: const Icon(Icons.logout),
                  label: const Text('Sair do sistema'),
                ),
                FilledButton.icon(
                  onPressed: authorizing
                      ? null
                      : () async {
                          if (!formKey.currentState!.validate()) return;
                          update(() => authorizing = true);
                          // Modo "senha do caixa": o servidor verifica a senha do
                          // restaurante e aprova — sem precisar de login de gerente.
                          if (cashMode) {
                            try {
                              cashSession = await api.post(
                                '/cash-register/${cashSession!['id']}/approve/',
                                body: {
                                  'reason': reason.text.trim(),
                                  'cash_password': cashPassword.text,
                                },
                                accessToken: token,
                              );
                              if (dialogContext.mounted) {
                                Navigator.pop(dialogContext);
                              }
                              await _load();
                            } catch (error) {
                              if (mounted) _error(error);
                              update(() => authorizing = false);
                            } finally {
                              cashPassword.clear();
                            }
                            return;
                          }
                          String? temporaryAccess;
                          String? temporaryRefresh;
                          try {
                            final login = await api.post(
                              '/auth/login/',
                              body: {
                                'username': username.text.trim(),
                                'password': password.text,
                                // Autorização gerencial temporária: só usa o token
                                // (Bearer), sem cookies do navegador.
                                'no_cookie': true,
                              },
                            );
                            temporaryAccess = '${login['access']}';
                            temporaryRefresh = '${login['refresh']}';
                            final user = login['user'] as Map<String, dynamic>?;
                            final allowed =
                                user?['is_superuser'] == true ||
                                {
                                  'admin',
                                  'owner',
                                  'manager',
                                }.contains('${user?['profile_type']}');
                            if (!allowed) {
                              throw const ApiException(
                                'O usuário informado não possui permissão gerencial.',
                                statusCode: 403,
                              );
                            }
                            cashSession = await api.post(
                              '/cash-register/${cashSession!['id']}/approve/',
                              body: {'reason': reason.text.trim()},
                              accessToken: temporaryAccess,
                            );
                            if (dialogContext.mounted) {
                              Navigator.pop(dialogContext);
                            }
                            await _load();
                          } catch (error) {
                            if (mounted) _error(error);
                            update(() => authorizing = false);
                          } finally {
                            password.clear();
                            if (temporaryAccess != null &&
                                temporaryRefresh != null) {
                              try {
                                await api.post(
                                  '/auth/logout/',
                                  body: {
                                    'refresh': temporaryRefresh,
                                    'no_cookie': true,
                                  },
                                  accessToken: temporaryAccess,
                                );
                              } catch (_) {}
                            }
                          }
                        },
                  icon: authorizing
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.verified_user_outlined),
                  label: const Text('Aprovar e concluir fechamento'),
                ),
              ],
            ),
          ),
        ),
      );
    } finally {
      divergenceDialogOpen = false;
      username.dispose();
      password.dispose();
      cashPassword.dispose();
      reason.dispose();
    }
  }

  Widget _divergenceValue(
    String label,
    String value, {
    bool emphasized = false,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label),
        Text(
          value,
          style: TextStyle(
            fontSize: emphasized ? 18 : 16,
            fontWeight: FontWeight.w900,
            color: emphasized ? Theme.of(context).colorScheme.error : null,
          ),
        ),
      ],
    ),
  );

  String _differenceText(dynamic value) {
    final difference = _number(value);
    final description = difference < 0
        ? 'falta'
        : difference > 0
        ? 'sobra'
        : 'sem diferença';
    return '${_money(difference.abs())} ($description)';
  }

  void _goBack() {
    if (flowStep == 'payment' && activeOrder != null) {
      setState(() => flowStep = 'order');
    } else if (flowStep == 'context') {
      setState(() => flowStep = 'type');
    } else if (activeOrder != null) {
      _goHome();
    }
  }

  @override
  void dispose() {
    deviceAgent.stop();
    unawaited(orderStore.close());
    ordersSignalSubscription?.cancel();
    syncStatusSubscription?.cancel();
    topologyService?.removeListener(_onTopologyChanged);
    topologyService?.dispose();
    paymentReference.dispose();
    paymentAmount.dispose();
    ordersSearchDebounce?.cancel();
    ordersSearchController.dispose();
    super.dispose();
  }

  /// Publica a falha no alerta global, que sempre traz o botão de fechar.
  ///
  /// A mensagem do backend é repassada literalmente: uma inconsistência de
  /// caixa ("caixa já aberto em outro terminal", "sangria divergente") precisa
  /// chegar ao operador exatamente como o servidor a descreveu.
  void _error(Object error, {String? title, String? action}) {
    final center = ErrorCenterScope.read(context);
    if (error is ApiException) {
      center.reportApi(error, title: title, recommendedAction: action);
      return;
    }
    center.reportUnexpected(error, title: title);
  }

  /// Reporta falhas de abertura, fechamento e movimentos de caixa.
  ///
  /// A operação só é considerada concluída depois da confirmação do servidor;
  /// qualquer recusa vira um alerta que o operador fecha para corrigir os
  /// dados e repetir.
  void _cashError(Object error, String operation) => _error(
    error,
    title: 'Não foi possível $operation',
    action: 'Feche este alerta, revise os dados e tente novamente.',
  );

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

  Future<void> _chooseTable() async {
    final table = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Selecionar mesa'),
        content: SizedBox(
          width: 620,
          child: GridView.builder(
            shrinkWrap: true,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 5,
              childAspectRatio: 1.25,
              crossAxisSpacing: 10,
              mainAxisSpacing: 10,
            ),
            itemCount: tables.length,
            itemBuilder: (_, index) {
              final item = tables[index];
              final occupied = item['current_order_id'] != null;
              return InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => Navigator.pop(context, item),
                child: Ink(
                  decoration: BoxDecoration(
                    color: occupied
                        ? Colors.orange.shade50
                        : Colors.green.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: occupied
                          ? Colors.orange.shade300
                          : Colors.green.shade300,
                    ),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        '${item['number']}',
                        style: const TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      Text(
                        occupied ? 'Em uso' : 'Livre',
                        style: const TextStyle(fontSize: 12),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
    if (table == null) return;
    await _openTable(table);
  }

  Future<void> _openTable(Map<String, dynamic> table) async {
    await _work(() async {
      selectedTable = table;
      final currentId = table['current_order_id'];
      final order = currentId != null
          ? await api.get('/orders/$currentId/', accessToken: token)
          : await api.post(
              '/orders/open-table/',
              body: {'table': table['id']},
              accessToken: token,
            );
      activeOrder = _completeOfflineOrder(order, type: 'table', table: table);
      if (_isOfflinePending(activeOrder)) {
        orderItems = [];
        table['status'] = 'occupied';
        table['current_order_id'] = activeOrder!['id'];
        if (mounted) setState(() {});
      } else {
        await _refreshOrder();
      }
      flowStep = 'order';
    });
  }

  /// Abre (ou retoma) o pedido de uma comanda.
  ///
  /// Espelha [_openTable]: comanda livre cria o pedido, comanda em uso retoma
  /// o que já existe. Quem decide é o servidor (`/orders/open-command/`), para
  /// que dois caixas lendo a mesma comanda não criem dois pedidos.
  Future<void> _openCommand(Map<String, dynamic> command) async {
    await _work(() async {
      selectedCommand = command;
      final currentId = command['current_order_id'];
      final order = currentId != null
          ? await api.get('/orders/$currentId/', accessToken: token)
          : await api.post(
              '/orders/open-command/',
              body: {'command': command['id']},
              accessToken: token,
            );
      activeOrder = _completeOfflineOrder(
        order,
        type: 'command',
        command: command,
      );
      if (_isOfflinePending(activeOrder)) {
        orderItems = [];
        command['status'] = 'occupied';
        command['current_order_id'] = activeOrder!['id'];
        if (mounted) setState(() {});
      } else {
        await _refreshOrder();
      }
      flowStep = 'order';
    });
  }

  Future<void> _selectOrderType(String type) async {
    orderType = type;
    if (type == 'table' || type == 'command') {
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
          return AlertDialog(
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
        builder: (context, update) => AlertDialog(
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
    if (type == 'table') {
      await _chooseTable();
      return;
    }
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
      if (_isOfflinePending(activeOrder)) {
        orderItems = [];
        if (mounted) setState(() {});
      } else {
        await _refreshOrder();
      }
      flowStep = 'order';
    });
  }

  Future<void> _refreshOrder() async {
    if (activeOrder == null) return;
    if (_isOfflinePending(activeOrder) ||
        '${activeOrder!['id']}'.startsWith('offline-')) {
      final items = activeOrder!['items'] as List? ?? orderItems;
      orderItems = items.cast<Map<String, dynamic>>();
      if (mounted) setState(() {});
      return;
    }
    final scope = api.sessionScope;
    try {
      final fresh = await api.get(
        '/orders/${activeOrder!['id']}/',
        accessToken: token,
      );
      activeOrder = scope == null
          ? fresh
          : await orderStore.saveFromServer(fresh, scope: scope);
    } on ApiException catch (error) {
      // Sem rede, a cópia local é a versão boa: ela tem as edições que ainda
      // não subiram. Esvaziar a tela aqui perderia o trabalho do operador.
      if (!error.isConnectivity) rethrow;
      final local = scope == null
          ? null
          : await orderStore.read('${activeOrder!['id']}', scope: scope);
      if (local != null) activeOrder = local;
      if (mounted) _warnLocalOrderData();
    }
    final items = activeOrder!['items'] as List? ?? [];
    orderItems = items
        .cast<Map<String, dynamic>>()
        .where((item) => item['status'] != 'voided')
        .toList();
    if (mounted) setState(() {});
  }

  bool _isOfflinePending(Map<String, dynamic>? value) =>
      OrderPresenter.isOffline(value);

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

  /// Registra o item lançado sem rede na memória **e** no disco.
  ///
  /// Guardar só em memória fazia a edição sumir ao sair da tela e voltar: a
  /// releitura pegava a cópia antiga, que não conhecia o item.
  Future<void> _addOfflineItem(
    Map<String, dynamic> response,
    Map<String, dynamic> product, {
    required double quantity,
    String customerNote = '',
  }) async {
    final item = OrderPresenter.offlineItem(
      response: response,
      product: product,
      quantity: quantity,
      customerNote: customerNote,
    );
    orderItems = [...orderItems, item];
    activeOrder = OrderPresenter.withItems(activeOrder!, orderItems);

    final scope = api.sessionScope;
    if (scope != null) {
      final persisted = await orderStore.addItem(
        '${activeOrder!['id']}',
        item,
        scope: scope,
      );
      // O store recalcula os totais; usar o resultado dele mantém a tela e o
      // disco com exatamente o mesmo valor.
      if (persisted != null) activeOrder = persisted;
    }
    if (mounted) setState(() {});
  }

  /// Marca o item como cancelado na cópia local.
  Future<void> _voidOfflineItem(String itemId) async {
    final scope = api.sessionScope;
    final order = activeOrder;
    if (scope == null || order == null) return;
    final persisted = await orderStore.voidItem(
      '${order['id']}',
      itemId,
      scope: scope,
    );
    if (persisted == null) return;
    activeOrder = persisted;
    orderItems = (persisted['items'] as List? ?? const [])
        .cast<Map<String, dynamic>>()
        .where((item) => item['status'] != 'voided')
        .toList();
    if (mounted) setState(() {});
  }

  Future<void> _configureProduct(Map<String, dynamic> product) async {
    if (cashSession == null) {
      _error(
        const ApiException('Abra o caixa antes de iniciar pedidos no PDV.'),
      );
      return;
    }
    if (activeOrder == null) {
      await _chooseTable();
      if (activeOrder == null) return;
    }
    if (!mounted) return;
    if (product['pricing_unit'] == 'kg') {
      await _weighProduct(product);
      return;
    }
    final config = await showProductConfigDialog(context, product);
    if (config == null) return;
    await _work(() async {
      final response = await api.post(
        '/orders/${activeOrder!['id']}/items/',
        body: {
          'product': product['id'],
          'quantity': config.quantity,
          'variations': config.variationId == null
              ? []
              : [config.variationId],
          'addons': config.addonIds,
          'customer_note': config.customerNote,
        },
        accessToken: token,
      );
      if (_isOfflinePending(response)) {
        _addOfflineItem(
          response,
          product,
          quantity: config.quantity.toDouble(),
          customerNote: config.customerNote,
        );
      } else {
        await _refreshOrder();
      }
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
        builder: (context, update) => AlertDialog(
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
                    borderRadius: BorderRadius.circular(12),
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
                              : Theme.of(context).colorScheme.onSurfaceVariant,
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
                                  update(() => readingMessage = error.message);
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
                        label: Text(readingScale ? 'Lendo...' : 'Ler balança'),
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
                              double.tryParse(value.replaceAll(',', '.')) ?? 0;
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
              onPressed: weight > 0 ? () => Navigator.pop(context, true) : null,
              child: const Text('Adicionar ao pedido'),
            ),
          ],
        ),
      ),
    );
    if (accepted != true) return;
    await _work(() async {
      final response = await api.post(
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
      if (_isOfflinePending(response)) {
        _addOfflineItem(
          response,
          product,
          quantity: weight,
          customerNote: note.text.trim(),
        );
      } else {
        await _refreshOrder();
      }
    });
  }

  Future<void> _voidItem(Map<String, dynamic> item) async {
    final reason = await ItemVoidReasonDialog.show(
      context,
      itemName: '${item['product_name'] ?? 'Item do pedido'}',
    );
    if (reason == null || !mounted) return;

    await _work(() async {
      final response = await api.delete(
        '/orders/${activeOrder!['id']}/items/${item['id']}/void/',
        body: {'reason': reason},
        accessToken: token,
      );
      if (_isOfflinePending(response)) {
        await _voidOfflineItem('${item['id']}');
      } else {
        await _refreshOrder();
      }
    });
  }

  Future<void> _finishOrder() async {
    if (activeOrder == null || orderItems.isEmpty) return;
    final nextStep = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
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
              const Text(
                'A taxa de serviço configurada no restaurante será calculada automaticamente.',
                style: TextStyle(fontSize: 12),
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
          FilledButton(
            onPressed: () => Navigator.pop(context, 'payment'),
            child: const Text('Ir para pagamento'),
          ),
        ],
      ),
    );
    if (nextStep == null) return;
    final closed = await _work(() async {
      final hasPendingItems = orderItems.any(
        (item) => item['status'] == 'pending',
      );
      if (hasPendingItems) {
        await api.post(
          '/orders/${activeOrder!['id']}/send-to-kitchen/',
          body: const {},
          accessToken: token,
        );
      }
      final alreadyAwaitingPayment =
          activeOrder!['status'] == 'awaiting_payment';
      final order = alreadyAwaitingPayment && !hasPendingItems
          ? activeOrder!
          : await api.post(
              '/orders/${activeOrder!['id']}/close/',
              body: const {},
              accessToken: token,
            );
      activeOrder = order;
      return order;
    });
    if (closed == null) return;
    if (nextStep == 'later') {
      // O pedido já foi fechado acima. A nota é um efeito colateral: se a
      // impressora falhar, o operador não pode ficar preso na tela do pedido
      // com uma venda que, do ponto de vista do caixa, já terminou.
      var printed = false;
      try {
        final printJob = await api.post(
          '/orders/${closed['id']}/print/',
          body: const {'job_type': 'receipt'},
          accessToken: token,
        );
        await _handlePrintJob(printJob);
        printed = true;
      } catch (error) {
        if (mounted) {
          _error(
            error,
            title: 'O pedido foi fechado, mas a nota não saiu',
            action: 'Reimprima pela tela de Pedidos quando quiser.',
          );
        }
      }
      if (mounted) {
        showAppToast(
          context,
          printed
              ? 'Pedido deixado pendente de pagamento. Nota gerada.'
              : 'Pedido deixado pendente de pagamento.',
        );
      }
      await _goHome();
      return;
    }
    await _paymentDialog();
  }

  /// Imprime a NOTA COMPLETA DO CLIENTE (receipt: itens + valores + total) do
  /// pedido atual, a qualquer momento — sem finalizar/enviar à cozinha.
  Future<void> _printCustomerReceipt([
    Map<String, dynamic>? selectedOrder,
  ]) async {
    final order = selectedOrder ?? activeOrder;
    if (order == null || printingReceipt) return;
    setState(() => printingReceipt = true);
    try {
      final printers = await _list(
        '/printers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      );
      if (!mounted) return;
      if (printers.isEmpty) {
        _error(
          const ApiException(
            'Nenhuma impressora ativa foi cadastrada para este restaurante.',
          ),
        );
        return;
      }
      final printerId = await showDialog<String>(
        context: context,
        builder: (_) => PrinterSelectionDialog(
          printers: printers,
          title: 'Imprimir nota do cliente',
          summary: 'Pedido #${order['sequence']} · ${_money(order['total'])}',
          description:
              'A nota contém restaurante, cliente ou mesa, itens, observações, pagamentos e totais.',
        ),
      );
      if (printerId == null) return;
      final printJob = await _work(
        () => api.post(
          '/orders/${order['id']}/print/',
          body: {
            'job_type': 'receipt',
            'printer': printerId,
            'manual_only': true,
          },
          accessToken: token,
        ),
      );
      if (printJob == null) return;
      final printer = printJob['printer'] as Map<String, dynamic>?;
      if (printer == null) {
        _error(
          const ApiException('A impressora selecionada não foi encontrada.'),
        );
        return;
      }
      final result = await _work(() async {
        await deviceAgent.printJobManually(printJob, printer);
        return true;
      });
      if (result == true && mounted) {
        showAppToast(context, 'Nota do cliente impressa com sucesso.');
      }
    } finally {
      if (mounted) setState(() => printingReceipt = false);
    }
  }

  /// Operação fiscal separada da comanda: emite a NFC-e (POST /invoices/emit)
  /// e, se conseguir, imprime o DANFE (POST /invoices/{id}/print). Exige
  /// conexão real com o backend — `ApiClient._requiresOnline` já bloqueia o
  /// enfileiramento offline dessas rotas, então uma falha aqui chega como
  /// [ApiException] normal, tratada pelo [_error] de sempre.
  Future<void> _emitFiscalInvoice(Map<String, dynamic> order) async {
    if (emittingInvoice) return;
    setState(() => emittingInvoice = true);
    try {
      final invoice = await _work(
        () => api.post(
          '/invoices/emit/',
          body: {
            'order': order['id'],
            if (selectedCustomer?['document'] != null) 'cpf': selectedCustomer!['document'],
            if (selectedCustomer?['name'] != null) 'cpf_name': selectedCustomer!['name'],
          },
          accessToken: token,
        ),
        errorTitle: 'Não foi possível emitir a NFC-e',
      );
      if (invoice == null || !mounted) return;

      if (invoice['emission_type'] == '9') {
        showAppToast(
          context,
          'NFC-e emitida em contingência — será retransmitida quando a conexão com a SEFAZ voltar.',
        );
      } else if (invoice['status'] == 'issued') {
        showAppToast(context, 'NFC-e autorizada.');
      } else {
        showAppToast(context, 'NFC-e emitida, aguardando autorização.');
      }

      final printers = await _list(
        '/printers/',
        query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
      );
      if (!mounted || printers.isEmpty) return;
      final printerId = await showDialog<String>(
        context: context,
        builder: (_) => PrinterSelectionDialog(
          printers: printers,
          title: 'Imprimir DANFE NFC-e',
          summary: 'Pedido #${order['sequence']} · NFC-e ${invoice['number'] ?? ''}',
          description: 'O DANFE traz a chave de acesso e o QR Code de consulta da nota.',
        ),
      );
      if (printerId == null) return;
      final printJob = await _work(
        () => api.post(
          '/invoices/${invoice['id']}/print/',
          body: {'printer': printerId},
          accessToken: token,
        ),
      );
      if (printJob == null) return;
      final printer = printJob['printer'] as Map<String, dynamic>?;
      if (printer == null) {
        _error(const ApiException('A impressora selecionada não foi encontrada.'));
        return;
      }
      final result = await _work(() async {
        await deviceAgent.printJobManually(printJob, printer);
        return true;
      });
      if (result == true && mounted) {
        showAppToast(context, 'DANFE impresso com sucesso.');
      }
    } finally {
      if (mounted) setState(() => emittingInvoice = false);
    }
  }

  Future<void> _paymentDialog() async {
    try {
      await _preparePaymentPage();
    } catch (error) {
      if (mounted) _error(error);
    }
  }

  /// Pagamentos já registrados no pedido.
  ///
  /// Offline a lista vem do cache; se nem isso existir, o pedido ainda não tem
  /// pagamento e a lista vazia é a resposta correta — não um erro.
  Future<List<Map<String, dynamic>>> _loadRegisteredPayments() async {
    try {
      final response = await api.get(
        '/orders/${activeOrder!['id']}/payments/',
        accessToken: token,
      );
      return ((response['results'] ?? response['data'] ?? <dynamic>[]) as List)
          .cast<Map<String, dynamic>>();
    } on ApiException catch (error) {
      if (!error.isConnectivity) rethrow;
      return registeredPayments;
    }
  }

  Future<void> _preparePaymentPage() async {
    paymentMethods = await _list(
      '/payments/methods/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    );
    // Sem rede e sem cópia guardada, o pedido simplesmente ainda não tem
    // pagamentos — tratar isso como falha impediria de receber offline, que é
    // exatamente quando o operador mais precisa concluir a venda.
    registeredPayments = await _loadRegisteredPayments();
    selectedPaymentMethod = paymentMethods.isEmpty
        ? null
        : '${paymentMethods.first['id']}';
    paymentDigits = (remainingTotal * 100).round().toString();
    _syncPaymentAmount();
    paymentReference.clear();
    setState(() => flowStep = 'payment');
  }

  void _pressPaymentKey(String key) {
    setState(() {
      if (key == 'clear') {
        paymentDigits = '0';
      } else if (key == 'back') {
        paymentDigits = paymentDigits.length <= 1
            ? '0'
            : paymentDigits.substring(0, paymentDigits.length - 1);
      } else {
        paymentDigits = paymentDigits == '0' ? key : '$paymentDigits$key';
        if (paymentDigits.length > 9) {
          paymentDigits = paymentDigits.substring(0, 9);
        }
      }
      _syncPaymentAmount();
    });
  }

  void _syncPaymentAmount() {
    paymentAmount.text = paymentValue.toStringAsFixed(2).replaceAll('.', ',');
    paymentAmount.selection = TextSelection.collapsed(
      offset: paymentAmount.text.length,
    );
  }

  /// Débito/crédito não é escolhido à parte: o próprio método de pagamento
  /// selecionado já diz qual é ("Cartão de Débito", "Cartão de Crédito"),
  /// como cadastrado em Formas de pagamento. Isso só preenche o metadado
  /// para relatórios; nada no backend valida esse texto.
  String _cardSubtypeFor(Map<String, dynamic> method) {
    final name = '${method['name']}'.toLowerCase();
    if (name.contains('débito') || name.contains('debito')) return 'debit';
    return 'credit';
  }

  Future<void> _addSplitPayment() async {
    if (selectedPaymentMethod == null || paymentValue <= 0) return;
    final method = paymentMethods.firstWhere(
      (item) => '${item['id']}' == selectedPaymentMethod,
    );
    if (method['method_type'] != 'cash' &&
        paymentValue > remainingTotal + .009) {
      _error(
        const ApiException(
          'Somente dinheiro pode ter valor recebido maior que o restante.',
        ),
      );
      return;
    }
    final result = await _work(
      () => api.post(
        '/orders/${activeOrder!['id']}/pay/',
        body: {
          'payment_method': selectedPaymentMethod,
          'amount': paymentValue.toStringAsFixed(2),
          'idempotency_key':
              'flutter-${activeOrder!['id']}-${DateTime.now().microsecondsSinceEpoch}',
          'metadata': {
            'card_subtype': method['method_type'] == 'card'
                ? _cardSubtypeFor(method)
                : '',
            'reference': paymentReference.text.trim(),
            'source': 'flutter_pdv',
          },
        },
        accessToken: token,
      ),
    );
    if (result == null) return;
    if (_isOfflinePending(result)) {
      // O pagamento está na fila. Ele já conta para o total recebido, senão o
      // operador nunca chegaria a zerar o restante e fechar a venda sem rede.
      // A chave de idempotência garante que o reenvio não cobre de novo.
      registeredPayments = [...registeredPayments, result];
    } else {
      registeredPayments = await _loadRegisteredPayments();
      if (method['method_type'] == 'cash') {
        try {
          cashSession = await api.get(
            '/cash-register/current/',
            accessToken: token,
          );
        } on ApiException {
          // O pagamento já foi registrado; a atualização geral tenta de novo.
        }
      }
    }
    paymentDigits = (remainingTotal * 100).round().toString();
    _syncPaymentAmount();
    paymentReference.clear();
    setState(() {});
  }

  /// Remove um pagamento já confirmado, como no frontend web.
  ///
  /// Só se aplica a pagamentos com id real: um pagamento ainda na fila
  /// offline nunca chegou ao servidor, então não há o que cancelar lá — a
  /// remoção correta nesse caso é esperar a sincronização.
  Future<void> _removePayment(Map<String, dynamic> payment) async {
    final id = payment['id'];
    if (id == null || removingPaymentId != null) return;
    setState(() => removingPaymentId = '$id');
    try {
      await api.delete(
        '/orders/${activeOrder!['id']}/payments/$id/',
        accessToken: token,
      );
      registeredPayments = await _loadRegisteredPayments();
      paymentDigits = (remainingTotal * 100).round().toString();
      _syncPaymentAmount();
    } catch (error) {
      if (mounted) {
        _error(error, title: 'Não foi possível excluir o pagamento');
      }
    } finally {
      if (mounted) setState(() => removingPaymentId = null);
    }
  }

  Future<void> _completePaidOrder() async {
    if (remainingTotal > .009) {
      _error(const ApiException('Ainda existe um valor restante para pagar.'));
      return;
    }
    // Guarda o pedido antes do reset de estado abaixo — a oferta de NFC-e
    // ainda precisa dele (e do cliente selecionado, pro CPF na nota).
    final paidOrder = activeOrder;
    // O pagamento já foi registrado. O comprovante é efeito colateral: se a
    // impressora ou a rede falhar, o operador não pode ficar preso na tela de
    // pagamento com uma venda que, para o caixa, já terminou.
    try {
      final printJob = await api.post(
        '/orders/${activeOrder!['id']}/print/',
        body: const {'job_type': 'payment_receipt'},
        accessToken: token,
      );
      await _handlePrintJob(printJob);
    } catch (error) {
      if (mounted) {
        _error(
          error,
          title: 'O pagamento foi registrado, mas o comprovante não saiu',
          action: 'Reimprima pela tela de Pedidos quando quiser.',
        );
      }
    }

    // Emitir NFC-e é uma operação separada de imprimir a comanda — pergunta
    // antes de resetar a tela, sem forçar (o operador pode preferir emitir
    // depois, pela tela de Pedidos).
    if (mounted && paidOrder != null) {
      final shouldEmit = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.receipt_long_outlined),
              SizedBox(width: 10),
              Expanded(child: Text('Emitir NFC-e?')),
            ],
          ),
          content: const Text(
            'O comprovante interno já foi impresso. Deseja também emitir a '
            'nota fiscal (NFC-e) e imprimir o DANFE?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Agora não'),
            ),
            FilledButton.icon(
              onPressed: () => Navigator.pop(dialogContext, true),
              icon: const Icon(Icons.receipt_long),
              label: const Text('Emitir NFC-e'),
            ),
          ],
        ),
      );
      if (shouldEmit == true) {
        await _emitFiscalInvoice(paidOrder);
      }
    }

    if (!mounted) return;
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

  Future<void> _handlePrintJob(Map<String, dynamic> job) async {
    if (!mounted) return;
    final printer = job['printer'] as Map<String, dynamic>?;
    if (printer == null) {
      _error(
        const ApiException(
          'Nenhuma impressora ativa foi encontrada para este restaurante.',
        ),
      );
      return;
    }
    if (printer['auto_print'] == true) return;

    final shouldPrint = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.print_outlined),
            SizedBox(width: 10),
            Expanded(child: Text('Impressão manual')),
          ],
        ),
        content: Text(
          'A impressão automática está desativada para '
          '${printer['name']}. Deseja imprimir agora?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Agora não'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.pop(dialogContext, true),
            icon: const Icon(Icons.print),
            label: const Text('Imprimir agora'),
          ),
        ],
      ),
    );
    if (shouldPrint != true) return;
    final result = await _work(() async {
      await deviceAgent.printJobManually(job, printer);
      return <String, dynamic>{'printed': true};
    });
    if (result != null && mounted) {
      showAppToast(context, 'Impressão enviada com sucesso.');
    }
  }

  Future<void> _openCash() async {
    final userId = widget.controller.session!.user.id;
    final linked = stations
        .where(
          (station) => (station['operators'] as List? ?? [])
              .map((id) => '$id')
              .contains(userId),
        )
        .toList();
    if (linked.isEmpty) {
      _error(
        const ApiException('Seu usuário não está vinculado a nenhum caixa.'),
      );
      return;
    }
    var stationId = '${linked.first['id']}';
    final amount = TextEditingController(text: '0.00');
    final notes = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: const Text('Abrir caixa'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: stationId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Caixa'),
                  items: linked
                      .map(
                        (station) => DropdownMenuItem(
                          value: '${station['id']}',
                          child: Text('${station['name']}'),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => update(() => stationId = value!),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: amount,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Valor de abertura',
                    prefixText: r'R$ ',
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: notes,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: 'Observação',
                    helperText:
                        'Registre alguma informação relevante sobre a abertura.',
                  ),
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
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Abrir caixa'),
            ),
          ],
        ),
      ),
    );
    if (confirmed == true) {
      final result = await _work(() async {
        cashSession = await api.post(
          '/cash-register/open/',
          body: {
            'cash_station': stationId,
            'opening_amount': amount.text.replaceAll(',', '.'),
            'notes': notes.text.trim(),
          },
          accessToken: token,
        );
        setState(() {});
        return cashSession;
      }, onError: (error) => _cashError(error, 'abrir o caixa'));
      if (result != null) {
        await _goHome();
      }
    }
  }

  Future<void> _cashMovement(String type) async {
    final amount = TextEditingController();
    final reason = TextEditingController();
    final destination = TextEditingController();
    final isWithdrawal = type == 'withdrawal';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          isWithdrawal ? 'Registrar sangria' : 'Registrar suprimento',
        ),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Valor',
                  prefixText: r'R$ ',
                ),
              ),
              if (isWithdrawal) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: destination,
                  decoration: const InputDecoration(labelText: 'Destino'),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: reason,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Motivo obrigatório',
                ),
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
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirmar'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      final movement = await _work(() async {
        return api.post(
          '/cash-register/${cashSession!['id']}/$type/',
          body: {
            'amount': amount.text.replaceAll(',', '.'),
            'reason': reason.text.trim(),
            'destination': destination.text.trim(),
            'source': destination.text.trim(),
          },
          accessToken: token,
        );
      }, onError: (error) => _cashError(
        error,
        isWithdrawal ? 'registrar a sangria' : 'registrar o suprimento',
      ));
      if (movement != null && movement['status'] == 'pending') {
        setState(() => pendingCashMovement = movement);
        await _showMovementApproval();
      }
    }
  }

  Future<void> _showMovementApproval() async {
    final movement = pendingCashMovement;
    if (!mounted || movement == null || movementApprovalDialogOpen) return;
    movementApprovalDialogOpen = true;
    final username = TextEditingController();
    final password = TextEditingController();
    final managerReason = TextEditingController();
    final formKey = GlobalKey<FormState>();
    var authorizing = false;
    try {
      await showDialog<void>(
        context: context,
        barrierDismissible: true,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, update) => AlertDialog(
            title: Text(
              movement['movement_type'] == 'withdrawal'
                  ? 'Autorizar sangria'
                  : 'Autorizar suprimento',
            ),
            content: SizedBox(
              width: 480,
              child: Form(
                key: formKey,
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Movimentação pendente de ${_money(_number(movement['amount']).abs())}.',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text('Motivo: ${movement['reason']}'),
                      if ('${movement['destination'] ?? ''}'.isNotEmpty)
                        Text('Destino: ${movement['destination']}'),
                      const Divider(height: 30),
                      TextFormField(
                        controller: username,
                        autofocus: true,
                        decoration: const InputDecoration(
                          labelText: 'Usuário autorizador',
                          helperText: 'Gerente, administrador ou proprietário.',
                        ),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                            ? 'Informe o usuário.'
                            : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: password,
                        obscureText: true,
                        decoration: const InputDecoration(labelText: 'Senha'),
                        validator: (value) => value == null || value.isEmpty
                            ? 'Informe a senha.'
                            : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: managerReason,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Justificativa gerencial',
                        ),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                            ? 'Informe a justificativa.'
                            : null,
                      ),
                    ],
                  ),
                ),
              ),
            ),
            actions: [
              TextButton.icon(
                onPressed: authorizing
                    ? null
                    : () => Navigator.pop(dialogContext),
                icon: const Icon(Icons.minimize),
                label: const Text('Minimizar'),
              ),
              FilledButton.icon(
                onPressed: authorizing
                    ? null
                    : () async {
                        if (!formKey.currentState!.validate()) return;
                        update(() => authorizing = true);
                        String? temporaryAccess;
                        String? temporaryRefresh;
                        try {
                          final login = await api.post(
                            '/auth/login/',
                            body: {
                              'username': username.text.trim(),
                              'password': password.text,
                            },
                          );
                          temporaryAccess = '${login['access']}';
                          temporaryRefresh = '${login['refresh']}';
                          final user = login['user'] as Map<String, dynamic>?;
                          final allowed =
                              user?['is_superuser'] == true ||
                              {
                                'admin',
                                'owner',
                                'manager',
                              }.contains('${user?['profile_type']}');
                          if (!allowed) {
                            throw const ApiException(
                              'O usuário informado não possui permissão gerencial.',
                              statusCode: 403,
                            );
                          }
                          await api.post(
                            '/cash-register/${cashSession!['id']}/approve/',
                            body: {
                              'movement': movement['id'],
                              'reason': managerReason.text.trim(),
                            },
                            accessToken: temporaryAccess,
                          );
                          pendingCashMovement = null;
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext);
                          }
                          await _load();
                        } catch (error) {
                          if (mounted) _error(error);
                          update(() => authorizing = false);
                        } finally {
                          password.clear();
                          if (temporaryAccess != null &&
                              temporaryRefresh != null) {
                            try {
                              await api.post(
                                '/auth/logout/',
                                body: {'refresh': temporaryRefresh},
                                accessToken: temporaryAccess,
                              );
                            } catch (_) {}
                          }
                        }
                      },
                icon: authorizing
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.verified_user_outlined),
                label: const Text('Autorizar movimentação'),
              ),
            ],
          ),
        ),
      );
    } finally {
      movementApprovalDialogOpen = false;
      username.dispose();
      password.dispose();
      managerReason.dispose();
    }
  }

  Future<void> _closeCash() async {
    final amount = TextEditingController();
    final notes = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Fechar caixa'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Valor contado',
                  helperText:
                      'Informe o dinheiro físico contado no fechamento.',
                  prefixText: r'R$ ',
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: notes,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Observação',
                  helperText:
                      'Informe ocorrências ou justificativas do fechamento.',
                ),
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
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirmar fechamento'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await _work(() async {
        cashSession = await api.post(
          '/cash-register/${cashSession!['id']}/close/',
          body: {
            'actual_amount': amount.text.replaceAll(',', '.'),
            'notes': notes.text.trim(),
          },
          accessToken: token,
        );
        setState(() {});
      }, onError: (error) => _cashError(error, 'fechar o caixa'));
    }
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
      return Scaffold(
        appBar: AppBar(
          title: const Text(
            'StarChef PDV',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          actions: [
            IconButton(
              tooltip: widget.isDark ? 'Usar tema claro' : 'Usar tema escuro',
              onPressed: widget.onToggleTheme,
              icon: Icon(
                widget.isDark
                    ? Icons.light_mode_outlined
                    : Icons.dark_mode_outlined,
              ),
            ),
            IconButton(
              tooltip: 'Sair',
              onPressed: widget.controller.logout,
              icon: const Icon(Icons.logout),
            ),
          ],
        ),
        body: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 480),
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    offlineMode ? Icons.cloud_off : Icons.storefront_outlined,
                    size: 64,
                    color: scheme.primary,
                  ),
                  const SizedBox(height: 18),
                  Text(
                    offlineMode
                        ? 'Dados offline ainda não disponíveis'
                        : 'Não foi possível carregar os restaurantes',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    loadErrorMessage ??
                        'Conecte o PDV à internet ao menos uma vez para baixar os dados necessários.',
                    textAlign: TextAlign.center,
                    maxLines: 4,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 22),
                  FilledButton.icon(
                    onPressed: loading ? null : _load,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Tentar novamente'),
                  ),
                ],
              ),
            ),
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
            restaurantName:
                '${restaurants.firstWhere((item) => '${item['id']}' == selectedRestaurantId, orElse: () => restaurants.first)['trade_name'] ?? restaurants.first['name']}',
            onLogout: widget.controller.logout,
            showOrders: widget.controller.session!.user.canViewOrders,
            showScale:
                widget.controller.session!.user.canManageOrders ||
                widget.controller.session!.user.canProcessPayments,
            showSettings: true,
          ),
          Expanded(
            child: Scaffold(
              appBar: AppBar(
                titleSpacing: 20,
                title: Row(
                  children: [
                    Icon(Icons.restaurant_menu, color: scheme.primary),
                    if (!compactHeader) ...[
                      const SizedBox(width: 10),
                      const Text(
                        'StarChef PDV',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ],
                    const SizedBox(width: 12),
                    if (restaurants.length > 1)
                      Expanded(
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            value: selectedRestaurantId,
                            isExpanded: true,
                            borderRadius: BorderRadius.circular(12),
                            icon: const Icon(Icons.expand_more),
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
                            onChanged: busy
                                ? null
                                : (value) {
                                    if (value != null) _changeRestaurant(value);
                                  },
                          ),
                        ),
                      )
                    else
                      Expanded(
                        child: Text(
                          '${restaurants.first['trade_name'] ?? restaurants.first['name']}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: Theme.of(context).textTheme.bodyMedium,
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
                        detail: topologyService?.status.message ?? '',
                        onPressed: () =>
                            unawaited(_openTopologySettings()),
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
                  if (cashSession == null)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: FilledButton.icon(
                        onPressed: _openCash,
                        icon: const Icon(Icons.lock_open),
                        label: const Text('Abrir caixa'),
                      ),
                    )
                  else
                    PopupMenuButton<String>(
                      tooltip: 'Ações do caixa',
                      onSelected: (value) {
                        if (value == 'supply' || value == 'withdrawal') {
                          _cashMovement(value);
                        }
                        if (value == 'close') _closeCash();
                      },
                      itemBuilder: (_) => const [
                        PopupMenuItem(
                          value: 'supply',
                          child: ListTile(
                            leading: Icon(Icons.add_circle_outline),
                            title: Text('Suprimento'),
                          ),
                        ),
                        PopupMenuItem(
                          value: 'withdrawal',
                          child: ListTile(
                            leading: Icon(Icons.remove_circle_outline),
                            title: Text('Sangria'),
                          ),
                        ),
                        PopupMenuDivider(),
                        PopupMenuItem(
                          value: 'close',
                          child: ListTile(
                            leading: Icon(Icons.lock),
                            title: Text('Fechar caixa'),
                          ),
                        ),
                      ],
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 8,
                        ),
                        child: Container(
                          height: 40,
                          padding: const EdgeInsets.symmetric(horizontal: 14),
                          decoration: BoxDecoration(
                            color: scheme.primary,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.point_of_sale,
                                size: 18,
                                color: Colors.white,
                              ),
                              const SizedBox(width: 8),
                              Column(
                                mainAxisSize: MainAxisSize.min,
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    cashSessionFromCache
                                        ? 'Caixa (offline) · ${cashSession!['station']}'
                                        : 'Caixa aberto · ${cashSession!['station']}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 11,
                                      height: 1,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  const SizedBox(height: 3),
                                  Text(
                                    'Saldo ${_money(cashBalance)}',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 14,
                                      height: 1,
                                      fontWeight: FontWeight.w900,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(width: 6),
                              const Icon(
                                Icons.expand_more,
                                size: 18,
                                color: Colors.white,
                              ),
                            ],
                          ),
                        ),
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
                  const SizedBox(width: 10),
                ],
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
                        return Row(
                          children: [
                            Expanded(child: _catalog()),
                            SizedBox(width: cartWidth, child: _cart()),
                          ],
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
                            child: Card(
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
                        borderRadius: BorderRadius.circular(12),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(12),
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

  /// Barra de busca, filtros e ordenação da tela de Pedidos.
  Widget _ordersFilterBar() {
    final range = orderDateRange;
    final dateLabel = range == null
        ? 'Período'
        : '${_shortDate(range.start)} – ${_shortDate(range.end)}';
    final hasFilters =
        orderSearch.trim().isNotEmpty ||
        orderTypeFilter != null ||
        orderDateRange != null ||
        orderStatusFilter != 'pending' ||
        orderOrdering != '-opened_at';
    return Wrap(
      spacing: 12,
      runSpacing: 12,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        SizedBox(
          width: 300,
          child: TextField(
            controller: ordersSearchController,
            decoration: InputDecoration(
              prefixIcon: const Icon(Icons.search_rounded),
              hintText: 'Nº do pedido, cliente ou mesa...',
              suffixIcon: orderSearch.isEmpty
                  ? null
                  : IconButton(
                      tooltip: 'Limpar busca',
                      icon: const Icon(Icons.close_rounded, size: 18),
                      onPressed: () {
                        ordersSearchController.clear();
                        setState(() => orderSearch = '');
                        _onOrdersFilterChanged();
                      },
                    ),
            ),
            onChanged: (value) {
              setState(() => orderSearch = value);
              _onOrdersFilterChanged(debounce: true);
            },
          ),
        ),
        SizedBox(
          width: 230,
          child: DropdownButtonFormField<String>(
            initialValue: orderStatusFilter,
            // Sem `isExpanded` o rótulo selecionado usa a largura natural do
            // texto e estoura a caixa — "Pendentes de pagamento" não cabe em
            // 230 px com o texto ampliado.
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Situação'),
            items: const [
              DropdownMenuItem(
                value: 'pending',
                child: Text(
                  'Pendentes de pagamento',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(value: 'open', child: Text('Em aberto')),
              DropdownMenuItem(
                value: 'awaiting_payment',
                child: Text(
                  'Aguardando pagamento',
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              DropdownMenuItem(value: 'paid', child: Text('Pagos')),
              DropdownMenuItem(value: 'all', child: Text('Todos')),
            ],
            onChanged: (value) {
              setState(() => orderStatusFilter = value ?? 'pending');
              _onOrdersFilterChanged();
            },
          ),
        ),
        SizedBox(
          width: 180,
          child: DropdownButtonFormField<String?>(
            initialValue: orderTypeFilter,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Tipo'),
            items: const [
              DropdownMenuItem(value: null, child: Text('Todos os tipos')),
              DropdownMenuItem(value: 'table', child: Text('Mesa')),
              DropdownMenuItem(value: 'command', child: Text('Comanda')),
              DropdownMenuItem(value: 'counter', child: Text('Balcão')),
              DropdownMenuItem(value: 'takeaway', child: Text('Retirada')),
              DropdownMenuItem(value: 'delivery', child: Text('Delivery')),
            ],
            onChanged: (value) {
              setState(() => orderTypeFilter = value);
              _onOrdersFilterChanged();
            },
          ),
        ),
        SizedBox(
          width: 210,
          child: DropdownButtonFormField<String>(
            initialValue: orderOrdering,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Ordenar por'),
            items: const [
              DropdownMenuItem(
                value: '-opened_at',
                child: Text('Mais recentes', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: 'opened_at',
                child: Text('Mais antigos', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '-total',
                child: Text('Maior valor', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: 'total',
                child: Text('Menor valor', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: '-sequence',
                child: Text('Nº decrescente', overflow: TextOverflow.ellipsis),
              ),
              DropdownMenuItem(
                value: 'sequence',
                child: Text('Nº crescente', overflow: TextOverflow.ellipsis),
              ),
            ],
            onChanged: (value) {
              setState(() => orderOrdering = value ?? '-opened_at');
              _onOrdersFilterChanged();
            },
          ),
        ),
        _ordersDateRangeMenu(dateLabel),
        if (hasFilters)
          TextButton.icon(
            onPressed: () {
              ordersSearchController.clear();
              setState(() {
                orderSearch = '';
                orderTypeFilter = null;
                orderDateRange = null;
                orderStatusFilter = 'pending';
                orderOrdering = '-opened_at';
              });
              _onOrdersFilterChanged();
            },
            icon: const Icon(Icons.filter_alt_off_outlined),
            label: const Text('Limpar filtros'),
          ),
      ],
    );
  }

  Widget _ordersPartialWarning() {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.orange.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.orange.withValues(alpha: .4)),
      ),
      child: Row(
        children: [
          Icon(Icons.cloud_off_rounded, size: 18, color: scheme.onSurface),
          const SizedBox(width: 10),
          const Expanded(
            child: Text(
              'Sem conexão: a busca vale só para os pedidos já guardados '
              'neste caixa. Pedidos antigos podem não aparecer.',
            ),
          ),
        ],
      ),
    );
  }

  static String _shortDate(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/'
      '${value.month.toString().padLeft(2, '0')}';

  /// Menu compacto de período, ancorado no botão — em vez do seletor nativo,
  /// que abre um diálogo grande e cobre a tela para escolher só duas datas.
  /// Os atalhos cobrem o uso comum; "Personalizado" ainda cai no seletor
  /// nativo, só para quem realmente precisa de datas específicas.
  Widget _ordersDateRangeMenu(String label) {
    final today = DateTime.now();
    final startOfToday = DateTime(today.year, today.month, today.day);

    DateTimeRange lastDays(int count) => DateTimeRange(
      start: startOfToday.subtract(Duration(days: count - 1)),
      end: startOfToday,
    );

    void apply(DateTimeRange? range) {
      setState(() => orderDateRange = range);
      _onOrdersFilterChanged();
    }

    return MenuAnchor(
      builder: (context, controller, child) => OutlinedButton.icon(
        onPressed: () =>
            controller.isOpen ? controller.close() : controller.open(),
        icon: const Icon(Icons.date_range_outlined),
        label: Text(label),
      ),
      menuChildren: [
        MenuItemButton(
          onPressed: () => apply(DateTimeRange(start: startOfToday, end: startOfToday)),
          child: const Text('Hoje'),
        ),
        MenuItemButton(
          onPressed: () {
            final yesterday = startOfToday.subtract(const Duration(days: 1));
            apply(DateTimeRange(start: yesterday, end: yesterday));
          },
          child: const Text('Ontem'),
        ),
        MenuItemButton(
          onPressed: () => apply(lastDays(7)),
          child: const Text('Últimos 7 dias'),
        ),
        MenuItemButton(
          onPressed: () => apply(lastDays(30)),
          child: const Text('Últimos 30 dias'),
        ),
        MenuItemButton(
          onPressed: () => apply(
            DateTimeRange(
              start: DateTime(today.year, today.month, 1),
              end: startOfToday,
            ),
          ),
          child: const Text('Este mês'),
        ),
        const Divider(height: 1),
        MenuItemButton(
          onPressed: () => unawaited(_pickCustomDateRange()),
          child: const Text('Personalizado...'),
        ),
        if (orderDateRange != null)
          MenuItemButton(
            onPressed: () => apply(null),
            child: const Text('Limpar período'),
          ),
      ],
    );
  }

  Future<void> _pickCustomDateRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 2),
      lastDate: DateTime(now.year + 1),
      initialDateRange: orderDateRange,
      helpText: 'Período de abertura',
      saveText: 'Aplicar',
    );
    if (picked == null || !mounted) return;
    setState(() => orderDateRange = picked);
    _onOrdersFilterChanged();
  }

  Widget _ordersPage() {
    // A lista já vem filtrada do servidor (ou do cache, offline). Aqui só
    // sobra a situação, que cruza dois campos e por isso é decidida sempre
    // localmente — inclusive sobre o resultado do servidor.
    final filtered = orders.where(_matchesStatusFilter).toList();
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Pedidos',
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w900),
                    ),
                    const Text(
                      'Edite pedidos em aberto ou finalize pagamentos pendentes.',
                    ),
                  ],
                ),
              ),
              IconButton.filledTonal(
                tooltip: 'Atualizar pedidos',
                onPressed: () => _onOrdersFilterChanged(),
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _ordersFilterBar(),
          if (ordersPartial) ...[
            const SizedBox(height: 12),
            _ordersPartialWarning(),
          ],
          const SizedBox(height: 18),
          Expanded(
            child: Card(
              clipBehavior: Clip.antiAlias,
              child: ordersLoading
                  ? const Center(child: CircularProgressIndicator())
                  : filtered.isEmpty
                  ? const Center(
                      child: Text('Nenhum pedido encontrado neste filtro.'),
                    )
                  : LayoutBuilder(
                      builder: (context, constraints) {
                        // Precisa ser a mesma altura passada em
                        // dataRowMaxHeight abaixo: a tabela não rola
                        // internamente, então se a conta de quantas linhas
                        // cabem usar uma altura menor que a real, a tabela
                        // fica mais alta que o espaço disponível e estoura.
                        const rowHeight = 68.0;
                        final calculatedRows =
                            ((constraints.maxHeight - 180) / rowHeight)
                                .floor();
                        final rowsPerPage = calculatedRows.clamp(1, 10);
                        return SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: SizedBox(
                            width: constraints.maxWidth < 1000
                                ? 1000
                                : constraints.maxWidth,
                            child: PaginatedDataTable(
                              header: Text('${filtered.length} pedido(s)'),
                              // Não há seleção múltipla nessa lista; sem isso
                              // o DataTable mostra uma caixa de marcação por
                              // linha por padrão, sem nenhuma ação associada.
                              showCheckboxColumn: false,
                              // A linha padrão tem 48 px fixos, e a célula de
                              // ações traz botões que passam disso com o texto
                              // ampliado que o PDV usa — daí o estouro de
                              // poucos pixels repetido em toda linha. Dar
                              // altura suficiente resolve na origem, em vez de
                              // encolher os alvos de toque do operador.
                              dataRowMinHeight: 52,
                              dataRowMaxHeight: rowHeight,
                              rowsPerPage: rowsPerPage,
                              availableRowsPerPage: <int>{
                                rowsPerPage,
                                5,
                                10,
                                20,
                              }.toList()..sort(),
                              showFirstLastButtons: true,
                              columns: const [
                                DataColumn(label: Text('Pedido')),
                                DataColumn(label: Text('Tipo')),
                                DataColumn(label: Text('Cliente/Mesa')),
                                DataColumn(label: Text('Status')),
                                DataColumn(label: Text('Pagamento')),
                                DataColumn(label: Text('Total')),
                                DataColumn(label: Text('Ações')),
                              ],
                              source: OrderDataSource(
                                filtered,
                                money: _money,
                                onEdit: _editOrder,
                                onPay: _payOrder,
                                onPrint: _printCustomerReceipt,
                                allowEdit: widget
                                    .controller
                                    .session!
                                    .user
                                    .canManageOrders,
                                allowPayment: widget
                                    .controller
                                    .session!
                                    .user
                                    .canProcessPayments,
                              ),
                            ),
                          ),
                        );
                      },
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _startPanel() {
    final options = [
      ('table', 'Mesa', 'Atendimento no salão', Icons.table_restaurant),
      ('command', 'Comanda', 'Cartão de comanda', Icons.qr_code_2),
      ('counter', 'Balcão', 'Consumo rápido no local', Icons.storefront),
      (
        'takeaway',
        'Retirada',
        'Pedido para viagem',
        Icons.shopping_bag_outlined,
      ),
      ('delivery', 'Delivery', 'Pedido para entrega', Icons.delivery_dining),
    ];
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 940),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'Novo pedido',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Selecione o tipo de atendimento para começar.',
                style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 28),
              GridView.builder(
                shrinkWrap: true,
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 5,
                  mainAxisSpacing: 16,
                  crossAxisSpacing: 16,
                  // Cinco colunas deixam cada card mais estreito, então a
                  // legenda quebra em duas linhas; sem baixar a proporção o
                  // conteúdo estoura a altura da célula.
                  childAspectRatio: .92,
                ),
                itemCount: options.length,
                itemBuilder: (_, index) {
                  final option = options[index];
                  return Card(
                    elevation: 0,
                    clipBehavior: Clip.antiAlias,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                      side: BorderSide(color: Theme.of(context).dividerColor),
                    ),
                    child: InkWell(
                      onTap: () => _selectOrderType(option.$1),
                      child: Padding(
                        padding: const EdgeInsets.all(22),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              width: 48,
                              height: 48,
                              decoration: BoxDecoration(
                                color: Theme.of(
                                  context,
                                ).colorScheme.primaryContainer,
                                borderRadius: BorderRadius.circular(13),
                              ),
                              child: Icon(
                                option.$4,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                            ),
                            const Spacer(),
                            Text(
                              option.$2,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                            const SizedBox(height: 5),
                            Text(
                              option.$3,
                              style: TextStyle(
                                fontSize: 12,
                                color: Theme.of(
                                  context,
                                ).colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _tableContextPanel() => Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 980),
      child: Padding(
        padding: const EdgeInsets.all(30),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextButton.icon(
              onPressed: () => setState(() {
                flowStep = 'type';
                orderType = null;
              }),
              icon: const Icon(Icons.arrow_back),
              label: const Text('Voltar'),
            ),
            const SizedBox(height: 10),
            Text(
              'Selecione a mesa',
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 5),
            Text(
              'Mesas ocupadas retomam o pedido atual.',
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 22),
            Expanded(
              child: GridView.builder(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 170,
                  childAspectRatio: 1.05,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                ),
                itemCount: tables.length,
                itemBuilder: (_, index) {
                  final table = tables[index];
                  final occupied = table['current_order_id'] != null;
                  final color = occupied ? Colors.orange : Colors.green;
                  return Card(
                    elevation: 0,
                    clipBehavior: Clip.antiAlias,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                      side: BorderSide(color: color.shade300),
                    ),
                    child: InkWell(
                      onTap: () => _openTable(table),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Text(
                                  '${table['number']}',
                                  style: const TextStyle(
                                    fontSize: 24,
                                    fontWeight: FontWeight.w900,
                                  ),
                                ),
                                const Spacer(),
                                Container(
                                  width: 9,
                                  height: 9,
                                  decoration: BoxDecoration(
                                    color: color,
                                    shape: BoxShape.circle,
                                  ),
                                ),
                              ],
                            ),
                            const Spacer(),
                            Text(
                              occupied ? 'Ocupada' : 'Livre',
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                color: color.shade800,
                              ),
                            ),
                            Text(
                              '${table['capacity'] ?? 0} lugares · ${table['sector_name'] ?? 'Sem setor'}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 11,
                                color: Theme.of(
                                  context,
                                ).colorScheme.onSurfaceVariant,
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
      ),
    ),
  );

  /// Comandas ativas, filtradas por número, código escaneável ou cliente.
  ///
  /// A busca é local porque a lista inteira já veio no carregamento do PDV —
  /// e precisa continuar respondendo sem rede, que é quando o operador mais
  /// depende de achar a comanda pelo número impresso no cartão.
  List<Map<String, dynamic>> get visibleCommands {
    final term = commandSearch.trim().toLowerCase();
    final active = commands.where((item) => item['is_active'] != false);
    if (term.isEmpty) return active.toList();
    return active.where((item) {
      final haystack =
          '${item['number']} ${item['code'] ?? ''} '
                  '${item['customer_name'] ?? ''}'
              .toLowerCase();
      return haystack.contains(term);
    }).toList();
  }

  Widget _commandContextPanel() {
    final visible = visibleCommands;
    final free = commands
        .where((item) => item['is_active'] != false && item['status'] == 'free')
        .length;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 980),
        child: Padding(
          padding: const EdgeInsets.all(30),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextButton.icon(
                onPressed: () => setState(() {
                  flowStep = 'type';
                  orderType = null;
                }),
                icon: const Icon(Icons.arrow_back),
                label: const Text('Voltar'),
              ),
              const SizedBox(height: 10),
              Text(
                'Selecione a comanda',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                '$free ${free == 1 ? 'comanda livre' : 'comandas livres'} · '
                'toque numa em uso para retomar o pedido.',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                autofocus: true,
                onChanged: (value) => setState(() => commandSearch = value),
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search_rounded),
                  hintText: 'Buscar por número, código ou cliente...',
                ),
              ),
              const SizedBox(height: 18),
              Expanded(
                child: visible.isEmpty
                    ? Center(
                        child: Text(
                          commands.isEmpty
                              ? 'Nenhuma comanda cadastrada.'
                              : 'Nenhuma comanda encontrada.',
                        ),
                      )
                    : GridView.builder(
                        gridDelegate:
                            const SliverGridDelegateWithMaxCrossAxisExtent(
                              maxCrossAxisExtent: 170,
                              childAspectRatio: 1.05,
                              crossAxisSpacing: 12,
                              mainAxisSpacing: 12,
                            ),
                        itemCount: visible.length,
                        itemBuilder: (_, index) {
                          final command = visible[index];
                          final occupied =
                              command['current_order_id'] != null ||
                              command['status'] == 'occupied';
                          final color = occupied ? Colors.orange : Colors.green;
                          return Card(
                            elevation: 0,
                            clipBehavior: Clip.antiAlias,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14),
                              side: BorderSide(color: color.shade300),
                            ),
                            child: InkWell(
                              onTap: () => _openCommand(command),
                              child: Padding(
                                padding: const EdgeInsets.all(12),
                                child: Column(
                                  crossAxisAlignment:
                                      CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          '${command['number']}',
                                          style: const TextStyle(
                                            fontSize: 24,
                                            fontWeight: FontWeight.w900,
                                          ),
                                        ),
                                        const Spacer(),
                                        Container(
                                          width: 9,
                                          height: 9,
                                          decoration: BoxDecoration(
                                            color: color,
                                            shape: BoxShape.circle,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const Spacer(),
                                    Text(
                                      occupied ? 'Em uso' : 'Livre',
                                      style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        color: color.shade800,
                                      ),
                                    ),
                                    Text(
                                      '${command['customer_name']?.toString().trim().isNotEmpty == true ? command['customer_name'] : command['code'] ?? '—'}',
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: Theme.of(
                                          context,
                                        ).colorScheme.onSurfaceVariant,
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
        ),
      ),
    );
  }

  Widget _paymentPage() {
    final selected = selectedPaymentMethod == null || paymentMethods.isEmpty
        ? null
        : paymentMethods.firstWhere(
            (item) => '${item['id']}' == selectedPaymentMethod,
          );
    final needsReference = selected?['requires_reference'] == true;
    const keys = [
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
      'clear',
      '0',
      'back',
    ];
    return Padding(
      padding: const EdgeInsets.all(26),
      child: Row(
        children: [
          Expanded(
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    TextButton.icon(
                      onPressed: () => setState(() => flowStep = 'order'),
                      icon: const Icon(Icons.arrow_back),
                      label: const Text('Voltar ao pedido'),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Pagamento',
                      style: TextStyle(
                        fontSize: 27,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Pedido #${activeOrder!['sequence']}',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 24),
                    _paymentSummaryRow(
                      'Total do pedido',
                      _money(activeOrder!['total']),
                    ),
                    _paymentSummaryRow('Valor aplicado', _money(paidTotal)),
                    _paymentSummaryRow('Total recebido', _money(receivedTotal)),
                    if (changeTotal > .009)
                      Container(
                        width: double.infinity,
                        margin: const EdgeInsets.only(top: 14),
                        padding: const EdgeInsets.all(18),
                        decoration: BoxDecoration(
                          color: Colors.green.withValues(alpha: .12),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: Colors.green.withValues(alpha: .45),
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'TROCO A ENTREGAR',
                              style: TextStyle(
                                fontWeight: FontWeight.w800,
                                color: Colors.green,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              _money(changeTotal),
                              style: const TextStyle(
                                fontSize: 34,
                                fontWeight: FontWeight.w900,
                                color: Colors.green,
                              ),
                            ),
                            const Text(
                              'Entregue o troco e depois conclua o pedido.',
                            ),
                          ],
                        ),
                      ),
                    const Divider(height: 28),
                    _paymentSummaryRow(
                      'Restante',
                      _money(remainingTotal),
                      strong: true,
                    ),
                    const SizedBox(height: 22),
                    const Text(
                      'Pagamentos registrados',
                      style: TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 10),
                    Expanded(
                      child: registeredPayments.isEmpty
                          ? const Center(
                              child: Text('Nenhum pagamento registrado.'),
                            )
                          : ListView.separated(
                              itemCount: registeredPayments.length,
                              separatorBuilder: (_, _) => const Divider(),
                              itemBuilder: (_, index) {
                                final payment = registeredPayments[index];
                                return ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  leading: const CircleAvatar(
                                    child: Icon(Icons.check, size: 18),
                                  ),
                                  title: Text(
                                    '${payment['payment_method_name'] ?? 'Pagamento'}',
                                  ),
                                  subtitle:
                                      _number(payment['change_amount']) > .009
                                      ? Text(
                                          'Recebido: ${_money(_number(payment['amount']) + _number(payment['change_amount']))} · Troco: ${_money(payment['change_amount'])}',
                                        )
                                      : null,
                                  trailing: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Text(
                                        _money(payment['amount']),
                                        style: const TextStyle(
                                          fontWeight: FontWeight.w800,
                                        ),
                                      ),
                                      if (payment['id'] != null)
                                        IconButton(
                                          tooltip: 'Excluir pagamento',
                                          icon:
                                              removingPaymentId ==
                                                  '${payment['id']}'
                                              ? const SizedBox(
                                                  width: 18,
                                                  height: 18,
                                                  child: CircularProgressIndicator(
                                                    strokeWidth: 2,
                                                  ),
                                                )
                                              : const Icon(
                                                  Icons.delete_outline,
                                                  size: 20,
                                                ),
                                          onPressed: removingPaymentId == null
                                              ? () => _removePayment(payment)
                                              : null,
                                        ),
                                    ],
                                  ),
                                );
                              },
                            ),
                    ),
                    SizedBox(
                      width: double.infinity,
                      height: 52,
                      child: FilledButton.icon(
                        onPressed: remainingTotal <= .009
                            ? _completePaidOrder
                            : null,
                        icon: const Icon(Icons.check_circle),
                        label: const Text(
                          'Concluir pedido',
                          style: TextStyle(fontSize: 16),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 20),
          SizedBox(
            width: 430,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    DropdownButtonFormField<String>(
                      initialValue: selectedPaymentMethod,
                      isExpanded: true,
                      decoration: const InputDecoration(
                        labelText: 'Forma de pagamento',
                      ),
                      items: paymentMethods
                          .map(
                            (item) => DropdownMenuItem(
                              value: '${item['id']}',
                              child: Text('${item['name']}'),
                            ),
                          )
                          .toList(),
                      onChanged: (value) =>
                          setState(() => selectedPaymentMethod = value),
                    ),
                    if (needsReference) ...[
                      const SizedBox(height: 12),
                      TextField(
                        controller: paymentReference,
                        decoration: const InputDecoration(
                          labelText: 'Referência da transação',
                        ),
                      ),
                    ],
                    const SizedBox(height: 18),
                    TextField(
                      controller: paymentAmount,
                      readOnly: true,
                      textAlign: TextAlign.right,
                      style: const TextStyle(
                        fontSize: 34,
                        fontWeight: FontWeight.w900,
                      ),
                      decoration: const InputDecoration(
                        labelText: 'Valor do pagamento',
                        prefixText: r'R$ ',
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 18,
                        ),
                      ),
                    ),
                    if (pendingChange > .009) ...[
                      const SizedBox(height: 12),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 18,
                          vertical: 14,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.green.withValues(alpha: .12),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: Colors.green.withValues(alpha: .45),
                          ),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text(
                              'Troco',
                              style: TextStyle(fontWeight: FontWeight.w800),
                            ),
                            Text(
                              _money(pendingChange),
                              style: const TextStyle(
                                fontSize: 26,
                                fontWeight: FontWeight.w900,
                                color: Colors.green,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 14),
                    Expanded(
                      child: GridView.builder(
                        physics: const NeverScrollableScrollPhysics(),
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 3,
                              childAspectRatio: 1.6,
                              crossAxisSpacing: 10,
                              mainAxisSpacing: 10,
                            ),
                        itemCount: keys.length,
                        itemBuilder: (_, index) {
                          final key = keys[index];
                          return OutlinedButton(
                            onPressed: () => _pressPaymentKey(key),
                            child: key == 'back'
                                ? const Icon(Icons.backspace_outlined)
                                : key == 'clear'
                                ? const Text('C')
                                : Text(
                                    key,
                                    style: const TextStyle(
                                      fontSize: 20,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                          );
                        },
                      ),
                    ),
                    SizedBox(
                      width: double.infinity,
                      height: 52,
                      child: FilledButton.icon(
                        onPressed: paymentValue > 0 ? _addSplitPayment : null,
                        icon: const Icon(Icons.add_card),
                        label: Text(
                          pendingChange > .009
                              ? 'Receber e registrar troco'
                              : 'Adicionar pagamento',
                          style: const TextStyle(fontSize: 16),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _paymentSummaryRow(
    String label,
    String value, {
    bool strong = false,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontWeight: strong ? FontWeight.w800 : FontWeight.w500,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontSize: strong ? 24 : 16,
            fontWeight: FontWeight.w900,
            color: strong ? Theme.of(context).colorScheme.primary : null,
          ),
        ),
      ],
    ),
  );

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
    order: activeOrder,
    table: selectedTable,
    command: selectedCommand,
    customer: selectedCustomer,
    items: orderItems,
    money: _money,
    onVoidItem: _voidItem,
    onFinish: _finishOrder,
    onPrint: _printCustomerReceipt,
    printing: printingReceipt,
  );

  static double _number(dynamic value) => ValueFormatters.number(value);
  static String _money(dynamic value) => ValueFormatters.money(value);
}
