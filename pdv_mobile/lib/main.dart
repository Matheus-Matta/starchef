import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import 'core/config/api_settings.dart';
import 'core/network/api_client.dart';
import 'core/storage/offline_queue_store.dart';
import 'core/storage/session_store.dart';
import 'core/sync/backend_gateway.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/presentation/login_page.dart';
import 'features/auth/presentation/session_controller.dart';
import 'features/orders/data/order_drafts.dart';
import 'features/orders/data/orders_repository.dart';
import 'features/orders/presentation/orders_page.dart';
import 'features/printing/services/mobile_print_agent.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final settings = await ApiSettings.load();
  runApp(PdvMobileApp(settings: settings));
}

class PdvMobileApp extends StatefulWidget {
  const PdvMobileApp({super.key, required this.settings});

  final ApiSettings settings;

  @override
  State<PdvMobileApp> createState() => _PdvMobileAppState();
}

class _PdvMobileAppState extends State<PdvMobileApp> {
  late final ApiClient _api;
  late final BackendGateway _gateway;
  late final OrderDrafts _drafts;
  late final SessionController _controller;
  late final MobilePrintAgent _printAgent;
  String? _activeRestaurantId;

  @override
  void initState() {
    super.initState();
    _api = ApiClient(baseUrlProvider: () => widget.settings.baseUrl);
    _gateway = BackendGateway(api: _api, store: OfflineQueueStore());
    _drafts = OrderDrafts();
    _controller = SessionController(api: _api, store: SecureSessionStore());
    _printAgent = MobilePrintAgent(api: _api);
    _controller.addListener(_syncSessionServices);
    unawaited(_bootstrap());
  }

  Future<void> _bootstrap() async {
    await _gateway.restore();
    await _drafts.restore();
    await _controller.restore();
    _syncSessionServices();
  }

  void _syncSessionServices() {
    final session = _controller.session;
    _gateway.setAuthenticated(session != null);
    if (session == null) {
      if (_activeRestaurantId != null) _printAgent.stop();
      _activeRestaurantId = null;
    } else if (_activeRestaurantId != session.user.restaurantId) {
      _activeRestaurantId = session.user.restaurantId;
      unawaited(_printAgent.start(session.user.restaurantId));
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_syncSessionServices);
    _printAgent.dispose();
    _gateway.dispose();
    _controller.dispose();
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'StarChef PDV Mobile',
    debugShowCheckedModeBanner: false,
    themeMode: ThemeMode.system,
    theme: AppTheme.materialLight(),
    darkTheme: AppTheme.materialDark(),
    builder: (context, child) => ShadTheme(
      data: Theme.of(context).brightness == Brightness.dark
          ? AppTheme.shadDark()
          : AppTheme.shadLight(),
      child: child!,
    ),
    home: ListenableBuilder(
      listenable: _controller,
      builder: (context, _) => switch (_controller.stage) {
        SessionStage.restoring => const Scaffold(
          body: Center(child: CircularProgressIndicator()),
        ),
        SessionStage.loggedOut => LoginPage(
          controller: _controller,
          settings: widget.settings,
        ),
        SessionStage.ready => OrdersPage(
          controller: _controller,
          settings: widget.settings,
          printAgent: _printAgent,
          repository: OrdersRepository(
            api: _api,
            gateway: _gateway,
            session: _controller.session!,
            drafts: _drafts,
          ),
        ),
      },
    ),
  );
}
