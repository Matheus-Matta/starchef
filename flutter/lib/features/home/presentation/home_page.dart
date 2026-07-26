import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/formatters/value_formatters.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../devices/presentation/device_list_page.dart';
import '../../devices/presentation/printer_selection_dialog.dart';
import '../../devices/services/local_device_agent.dart';
import '../../orders/presentation/order_presenter.dart';
import '../../orders/presentation/order_data_source.dart';
import '../../orders/presentation/order_cart_panel.dart';
import '../../orders/presentation/item_void_reason_dialog.dart';
import '../data/pdv_repository.dart';
import 'pdv_presenter.dart';

class HomePage extends StatefulWidget {
  const HomePage({
    super.key,
    required this.controller,
    required this.isDark,
    required this.onToggleTheme,
    required this.isFullScreen,
    required this.onToggleFullScreen,
  });

  final AuthController controller;
  final bool isDark;
  final VoidCallback onToggleTheme;
  final bool isFullScreen;
  final VoidCallback onToggleFullScreen;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  ApiClient get api => widget.controller.repository.apiClient;
  String get token => widget.controller.session!.accessToken;
  String? get restaurantId => selectedRestaurantId;

  bool loading = true;
  bool busy = false;
  bool printingReceipt = false;
  bool divergenceDialogOpen = false;
  bool movementApprovalDialogOpen = false;
  String flowStep = 'type';
  String? orderType;
  String search = '';
  String? category;
  Map<String, dynamic>? cashSession;
  Map<String, dynamic>? activeOrder;
  Map<String, dynamic>? selectedTable;
  Map<String, dynamic>? selectedCustomer;
  Map<String, dynamic>? pendingCashMovement;
  List<Map<String, dynamic>> stations = [];
  List<Map<String, dynamic>> restaurants = [];
  List<Map<String, dynamic>> products = [];
  List<Map<String, dynamic>> categories = [];
  List<Map<String, dynamic>> tables = [];
  List<Map<String, dynamic>> orderItems = [];
  List<Map<String, dynamic>> paymentMethods = [];
  List<Map<String, dynamic>> registeredPayments = [];
  List<Map<String, dynamic>> orders = [];
  bool ordersLoading = false;
  String? loadErrorMessage;
  String orderStatusFilter = 'pending';
  String? selectedPaymentMethod;
  String paymentDigits = '0';
  String cardSubtype = 'debit';
  final paymentReference = TextEditingController();
  final paymentAmount = TextEditingController();
  String? selectedRestaurantId;
  late final LocalDeviceAgent deviceAgent;
  late final PdvRepository repository;
  late final PdvPresenter presenter;
  StreamSubscription<bool>? connectivitySubscription;
  bool offlineMode = false;
  int offlinePendingCount = 0;

  List<Map<String, dynamic>> get visibleProducts => products.where((product) {
    final matchesCategory =
        category == null || '${product['category']}' == category;
    final term = search.trim().toLowerCase();
    return matchesCategory &&
        (term.isEmpty || '${product['name']}'.toLowerCase().contains(term));
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
    connectivitySubscription = api.connectivityChanges.listen((online) async {
      final pending = await api.pendingOperations();
      if (!mounted) return;
      final shouldReload =
          online &&
          ((offlineMode && !loading) ||
              (offlinePendingCount > 0 && pending == 0));
      setState(() {
        offlineMode = !online;
        offlinePendingCount = pending;
      });
      if (shouldReload) unawaited(_load());
    });
    _load();
  }

  Future<List<Map<String, dynamic>>> _list(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    return repository.list(path, query: query);
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
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
      } on ApiException catch (error) {
        if (error.statusCode != 404) rethrow;
        cashSession = null;
        pendingCashMovement = null;
      }
    } catch (error) {
      loadErrorMessage = error is ApiException
          ? error.message
          : 'Não foi possível carregar os dados iniciais do PDV.';
      if (mounted) _error(error);
    } finally {
      if (mounted) {
        setState(() => loading = false);
        if (restaurantId != null) {
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
      selectedCustomer = null;
      orderItems = [];
      registeredPayments = [];
      paymentMethods = [];
      orderType = null;
      category = null;
      flowStep = 'type';
    });
    await _load();
  }

  Future<void> _openOrders() async {
    setState(() {
      flowStep = 'orders';
      activeOrder = null;
      ordersLoading = true;
    });
    try {
      final loaded = await _list(
        '/orders/',
        query: {'page_size': 300, 'ordering': '-opened_at'},
      );
      orders = loaded
          .where((item) => '${item['restaurant']}' == restaurantId)
          .toList();
    } catch (error) {
      if (mounted) _error(error);
    } finally {
      if (mounted) setState(() => ordersLoading = false);
    }
  }

  Future<void> _editOrder(Map<String, dynamic> order) async {
    final detail = await _work(
      () => api.get('/orders/${order['id']}/', accessToken: token),
    );
    if (detail == null) return;
    activeOrder = detail;
    orderType = '${detail['order_type']}';
    selectedTable = detail['table'] == null
        ? null
        : tables.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '${detail['table']}',
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
    final detail = await _work(
      () => api.get('/orders/${order['id']}/', accessToken: token),
    );
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

  Future<void> _goHome() async {
    setState(() {
      activeOrder = null;
      selectedTable = null;
      selectedCustomer = null;
      orderItems = [];
      registeredPayments = [];
      orderType = null;
      flowStep = 'type';
    });
    await _load();
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
    connectivitySubscription?.cancel();
    paymentReference.dispose();
    paymentAmount.dispose();
    super.dispose();
  }

  void _error(Object error) {
    final message = error is ApiException
        ? error.message
        : 'Não foi possível concluir a operação.';
    showCopyableError(context, message);
  }

  Future<T?> _work<T>(Future<T> Function() action) async {
    if (busy) return null;
    setState(() => busy = true);
    try {
      return await action();
    } catch (error) {
      if (mounted) _error(error);
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

  Future<void> _selectOrderType(String type) async {
    orderType = type;
    if (type == 'table') {
      setState(() => flowStep = 'context');
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
    activeOrder = await api.get(
      '/orders/${activeOrder!['id']}/',
      accessToken: token,
    );
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
  }) {
    return OrderPresenter.completeOfflineOrder(
      order,
      restaurantId: restaurantId,
      type: type,
      table: table,
    );
  }

  void _addOfflineItem(
    Map<String, dynamic> response,
    Map<String, dynamic> product, {
    required double quantity,
    String customerNote = '',
  }) {
    final item = OrderPresenter.offlineItem(
      response: response,
      product: product,
      quantity: quantity,
      customerNote: customerNote,
    );
    orderItems = [...orderItems, item];
    activeOrder = OrderPresenter.withItems(activeOrder!, orderItems);
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
    final variations = (product['variations'] as List? ?? [])
        .cast<Map<String, dynamic>>()
        .where((item) => item['is_active'] != false)
        .toList();
    final addons = (product['addons'] as List? ?? [])
        .cast<Map<String, dynamic>>()
        .where((item) => item['is_active'] != false)
        .toList();
    String? variation;
    final selectedAddons = <String>{};
    var quantity = 1;
    final note = TextEditingController();
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: Text(product['name'] as String),
          content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (variations.isNotEmpty) ...[
                    const Text(
                      'Variação',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    ...variations.map((item) {
                      final id = '${item['id']}';
                      return ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Icon(
                          variation == id
                              ? Icons.radio_button_checked
                              : Icons.radio_button_off,
                        ),
                        title: Text(
                          '${item['name']}  + ${_money(item['price_delta'])}',
                        ),
                        onTap: () => update(() => variation = id),
                      );
                    }),
                  ],
                  if (addons.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'Adicionais',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    ...addons.map(
                      (item) => CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          '${item['name']}  + ${_money(item['price'])}',
                        ),
                        value: selectedAddons.contains('${item['id']}'),
                        onChanged: (checked) => update(
                          () => checked == true
                              ? selectedAddons.add('${item['id']}')
                              : selectedAddons.remove('${item['id']}'),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Text(
                        'Quantidade',
                        style: TextStyle(fontWeight: FontWeight.w700),
                      ),
                      const Spacer(),
                      IconButton.filledTonal(
                        onPressed: quantity > 1
                            ? () => update(() => quantity--)
                            : null,
                        icon: const Icon(Icons.remove),
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16),
                        child: Text(
                          '$quantity',
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      IconButton.filled(
                        onPressed: () => update(() => quantity++),
                        icon: const Icon(Icons.add),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: note,
                    maxLines: 2,
                    decoration: const InputDecoration(
                      labelText: 'Observação',
                      hintText: 'Ex.: sem cebola',
                    ),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed:
                  product['requires_variation'] == true && variation == null
                  ? null
                  : () => Navigator.pop(context, true),
              child: const Text('Adicionar'),
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
          'quantity': quantity,
          'variations': variation == null ? [] : [variation],
          'addons': selectedAddons.toList(),
          'customer_note': note.text.trim(),
        },
        accessToken: token,
      );
      if (_isOfflinePending(response)) {
        _addOfflineItem(
          response,
          product,
          quantity: quantity.toDouble(),
          customerNote: note.text.trim(),
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
                                    showCopyableError(
                                      this.context,
                                      error.message,
                                    );
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
        orderItems = orderItems
            .where((row) => '${row['id']}' != '${item['id']}')
            .toList();
        activeOrder = {...activeOrder!, 'items': orderItems};
        if (mounted) setState(() {});
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
      final printJob = await _work(
        () => api.post(
          '/orders/${closed['id']}/print/',
          body: const {'job_type': 'receipt'},
          accessToken: token,
        ),
      );
      if (printJob == null) return;
      await _handlePrintJob(printJob);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Pedido enviado e deixado pendente de pagamento. Nota gerada.',
            ),
          ),
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
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Nota do cliente impressa com sucesso.'),
            duration: Duration(milliseconds: 1500),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => printingReceipt = false);
    }
  }

  Future<void> _paymentDialog() async {
    try {
      await _preparePaymentPage();
    } catch (error) {
      if (mounted) _error(error);
    }
  }

  Future<void> _preparePaymentPage() async {
    paymentMethods = await _list(
      '/payments/methods/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    );
    final response = await api.get(
      '/orders/${activeOrder!['id']}/payments/',
      accessToken: token,
    );
    registeredPayments =
        ((response['results'] ?? response['data'] ?? <dynamic>[]) as List)
            .cast<Map<String, dynamic>>();
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
            'card_subtype': method['method_type'] == 'card' ? cardSubtype : '',
            'reference': paymentReference.text.trim(),
            'source': 'flutter_pdv',
          },
        },
        accessToken: token,
      ),
    );
    if (result == null) return;
    final response = await api.get(
      '/orders/${activeOrder!['id']}/payments/',
      accessToken: token,
    );
    registeredPayments =
        ((response['results'] ?? response['data'] ?? <dynamic>[]) as List)
            .cast<Map<String, dynamic>>();
    if (method['method_type'] == 'cash') {
      try {
        cashSession = await api.get(
          '/cash-register/current/',
          accessToken: token,
        );
      } on ApiException {
        // O pagamento já foi registrado; a atualização geral tentará novamente.
      }
    }
    paymentDigits = (remainingTotal * 100).round().toString();
    _syncPaymentAmount();
    paymentReference.clear();
    setState(() {});
  }

  Future<void> _completePaidOrder() async {
    if (remainingTotal > .009) {
      _error(const ApiException('Ainda existe um valor restante para pagar.'));
      return;
    }
    final printJob = await _work(
      () => api.post(
        '/orders/${activeOrder!['id']}/print/',
        body: const {'job_type': 'payment_receipt'},
        accessToken: token,
      ),
    );
    if (printJob == null) return;
    await _handlePrintJob(printJob);
    setState(() {
      activeOrder = null;
      selectedTable = null;
      selectedCustomer = null;
      orderItems = [];
      registeredPayments = [];
      orderType = null;
      flowStep = 'type';
    });
    await _load();
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
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Impressão enviada com sucesso.')),
      );
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
      });
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
      });
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
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
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
      appBar: AppBar(
        titleSpacing: 20,
        title: Row(
          children: [
            Icon(Icons.restaurant_menu, color: scheme.primary),
            const SizedBox(width: 10),
            const Text(
              'StarChef PDV',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(width: 18),
            if (restaurants.length > 1)
              ConstrainedBox(
                constraints: const BoxConstraints(minWidth: 180, maxWidth: 280),
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
              Text(
                '${restaurants.first['trade_name'] ?? restaurants.first['name']}',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
          ],
        ),
        actions: [
          if (offlineMode || offlinePendingCount > 0)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
              child: Tooltip(
                message: offlineMode
                    ? 'Sem conexão. As alterações serão sincronizadas automaticamente.'
                    : '$offlinePendingCount alteração(ões) aguardando sincronização.',
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 11),
                  decoration: BoxDecoration(
                    color: offlineMode
                        ? scheme.errorContainer
                        : scheme.tertiaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        offlineMode ? Icons.cloud_off : Icons.cloud_sync,
                        size: 17,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        offlineMode
                            ? 'Modo offline'
                            : 'Sincronizando $offlinePendingCount',
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ],
                  ),
                ),
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
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
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
                            'Caixa aberto · ${cashSession!['station']}',
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
            tooltip: 'Atualizar',
            onPressed: _load,
            icon: const Icon(Icons.refresh),
          ),
          if (widget.controller.session!.user.canViewOrders)
            IconButton(
              tooltip: 'Ver pedidos',
              onPressed: _openOrders,
              icon: const Icon(Icons.receipt_long_outlined),
            ),
          if (widget.controller.session!.user.canManageDevices)
            PopupMenuButton<DeviceKind>(
              tooltip: 'Configurar equipamentos',
              icon: const Icon(Icons.settings_outlined),
              onSelected: _openDeviceSettings,
              itemBuilder: (_) => const [
                PopupMenuItem(
                  value: DeviceKind.printer,
                  child: ListTile(
                    leading: Icon(Icons.print_outlined),
                    title: Text('Impressoras'),
                  ),
                ),
                PopupMenuItem(
                  value: DeviceKind.scale,
                  child: ListTile(
                    leading: Icon(Icons.scale_outlined),
                    title: Text('Balanças'),
                  ),
                ),
              ],
            ),
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
            tooltip: widget.isFullScreen
                ? 'Sair da tela cheia (F11)'
                : 'Usar tela cheia (F11)',
            onPressed: widget.onToggleFullScreen,
            icon: Icon(
              widget.isFullScreen ? Icons.fullscreen_exit : Icons.fullscreen,
            ),
          ),
          IconButton(
            tooltip: 'Sair',
            onPressed: widget.controller.logout,
            icon: const Icon(Icons.logout),
          ),
          const SizedBox(width: 10),
        ],
      ),
      body: Stack(
        children: [
          if (flowStep == 'orders')
            _ordersPage()
          else if (activeOrder == null && flowStep == 'type')
            _startPanel()
          else if (activeOrder == null && flowStep == 'context')
            _tableContextPanel()
          else if (flowStep == 'payment')
            _paymentPage()
          else
            Row(
              children: [
                Expanded(flex: 5, child: _catalog()),
                SizedBox(width: 420, child: _cart()),
              ],
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
          if (busy)
            const Positioned.fill(
              child: ColoredBox(
                color: Color(0x33000000),
                child: Center(child: CircularProgressIndicator()),
              ),
            ),
        ],
      ),
    );
  }

  Widget _ordersPage() {
    final filtered = orders.where((order) {
      if (orderStatusFilter == 'all') return true;
      if (orderStatusFilter == 'pending') {
        return order['payment_status'] != 'paid' &&
            {'open', 'awaiting_payment'}.contains('${order['status']}');
      }
      return '${order['status']}' == orderStatusFilter;
    }).toList();
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
              SizedBox(
                width: 230,
                child: DropdownButtonFormField<String>(
                  initialValue: orderStatusFilter,
                  decoration: const InputDecoration(labelText: 'Situação'),
                  items: const [
                    DropdownMenuItem(
                      value: 'pending',
                      child: Text('Pendentes de pagamento'),
                    ),
                    DropdownMenuItem(value: 'open', child: Text('Em aberto')),
                    DropdownMenuItem(
                      value: 'awaiting_payment',
                      child: Text('Aguardando pagamento'),
                    ),
                    DropdownMenuItem(value: 'paid', child: Text('Pagos')),
                    DropdownMenuItem(value: 'all', child: Text('Todos')),
                  ],
                  onChanged: (value) =>
                      setState(() => orderStatusFilter = value ?? 'pending'),
                ),
              ),
              const SizedBox(width: 12),
              IconButton.filledTonal(
                tooltip: 'Atualizar pedidos',
                onPressed: _openOrders,
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
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
                        final calculatedRows =
                            ((constraints.maxHeight - 180) / 48).floor();
                        final rowsPerPage = calculatedRows.clamp(1, 10);
                        return SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: SizedBox(
                            width: constraints.maxWidth < 1000
                                ? 1000
                                : constraints.maxWidth,
                            child: PaginatedDataTable(
                              header: Text('${filtered.length} pedido(s)'),
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
                  crossAxisCount: 4,
                  mainAxisSpacing: 16,
                  crossAxisSpacing: 16,
                  childAspectRatio: 1.05,
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
                  childAspectRatio: 1.25,
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
                        padding: const EdgeInsets.all(16),
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

  Widget _paymentPage() {
    final selected = selectedPaymentMethod == null || paymentMethods.isEmpty
        ? null
        : paymentMethods.firstWhere(
            (item) => '${item['id']}' == selectedPaymentMethod,
          );
    final isCard = selected?['method_type'] == 'card';
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
                                  trailing: Text(
                                    _money(payment['amount']),
                                    style: const TextStyle(
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
                    if (isCard) ...[
                      const SizedBox(height: 12),
                      SegmentedButton<String>(
                        segments: const [
                          ButtonSegment(value: 'debit', label: Text('Débito')),
                          ButtonSegment(
                            value: 'credit',
                            label: Text('Crédito'),
                          ),
                        ],
                        selected: {cardSubtype},
                        onSelectionChanged: (value) =>
                            setState(() => cardSubtype = value.first),
                      ),
                    ],
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

  Widget _catalog() => Padding(
    padding: const EdgeInsets.fromLTRB(22, 18, 18, 18),
    child: Column(
      children: [
        Row(
          children: [
            Expanded(
              child: TextField(
                onChanged: (value) => setState(() => search = value),
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Buscar produto...',
                ),
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              width: 220,
              child: DropdownButtonFormField<String?>(
                initialValue: category,
                decoration: const InputDecoration(labelText: 'Categoria'),
                items: [
                  const DropdownMenuItem(
                    value: null,
                    child: Text('Todas as categorias'),
                  ),
                  ...categories.map(
                    (item) => DropdownMenuItem(
                      value: '${item['id']}',
                      child: Text(
                        '${item['name']}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ),
                ],
                onChanged: (value) => setState(() => category = value),
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),
        Expanded(
          child: GridView.builder(
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 260,
              mainAxisExtent: 150,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
            ),
            itemCount: visibleProducts.length,
            itemBuilder: (_, index) {
              final product = visibleProducts[index];
              return Card(
                elevation: 0,
                clipBehavior: Clip.antiAlias,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(13),
                  side: BorderSide(color: Theme.of(context).dividerColor),
                ),
                child: InkWell(
                  onTap: () => _configureProduct(product),
                  child: Padding(
                    padding: const EdgeInsets.all(15),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                '${product['name']}',
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 15,
                                ),
                              ),
                            ),
                            Icon(
                              Icons.add_circle,
                              color: Theme.of(context).colorScheme.primary,
                            ),
                          ],
                        ),
                        const Spacer(),
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${product['category_name'] ?? ''}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Theme.of(
                                    context,
                                  ).colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Text(
                              _money(product['current_price']),
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.primary,
                                fontWeight: FontWeight.w900,
                                fontSize: 16,
                              ),
                            ),
                          ],
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

  Widget _cart() => OrderCartPanel(
    order: activeOrder,
    table: selectedTable,
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
