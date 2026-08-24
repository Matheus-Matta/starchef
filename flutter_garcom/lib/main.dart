import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import 'core/config/app_env.dart';
import 'core/network/api_client.dart';
import 'core/relay/principal_client.dart';
import 'core/storage/session_store.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/presentation/login_page.dart';
import 'features/auth/presentation/principal_setup_page.dart';
import 'features/auth/presentation/session_controller.dart';
import 'features/orders/data/orders_repository.dart';
import 'features/orders/presentation/orders_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppEnv.load();
  runApp(const GarcomApp());
}

/// App do garçom.
///
/// Fluxo inteiro: login → pareamento com o Caixa Principal → pedidos abertos →
/// pedido. Sem pagamento em lugar nenhum: receber é do caixa, que tem gaveta,
/// maquininha e impressora.
class GarcomApp extends StatefulWidget {
  const GarcomApp({super.key});

  @override
  State<GarcomApp> createState() => _GarcomAppState();
}

class _GarcomAppState extends State<GarcomApp> {
  late final ApiClient _api;
  late final PrincipalClient _principal;
  late final SessionController _controller;

  @override
  void initState() {
    super.initState();
    _api = ApiClient(baseUrl: AppEnv.backendUrl);
    _principal = PrincipalClient();
    _controller = SessionController(
      api: _api,
      principalClient: _principal,
      store: SecureSessionStore(),
    );
    _controller.restore();
  }

  @override
  void dispose() {
    _controller.dispose();
    _api.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'StarChef Garçom',
    debugShowCheckedModeBanner: false,
    themeMode: ThemeMode.system,
    theme: AppTheme.materialLight(),
    darkTheme: AppTheme.materialDark(),
    // Mesma montagem do PDV: Material por baixo (diálogos, teclado, snackbar)
    // com os tokens do shadcn por cima, para as duas telas do produto — caixa
    // e salão — parecerem a mesma coisa.
    builder: (context, child) => ShadTheme(
      data: Theme.of(context).brightness == Brightness.dark
          ? AppTheme.shadDark()
          : AppTheme.shadLight(),
      child: child!,
    ),
    home: ListenableBuilder(
      listenable: _controller,
      // Uma etapa por vez, na ordem em que os dados aparecem: primeiro quem é
      // o garçom (login), depois para qual caixa vão os pedidos (pareamento).
      builder: (context, _) => switch (_controller.stage) {
        SessionStage.restoring => const Scaffold(
          body: Center(child: CircularProgressIndicator()),
        ),
        SessionStage.loggedOut => LoginPage(controller: _controller),
        SessionStage.unpaired => PrincipalSetupPage(controller: _controller),
        SessionStage.ready => OrdersPage(
          controller: _controller,
          repository: OrdersRepository(
            api: _api,
            principalClient: _principal,
            session: _controller.session!,
            principal: _controller.principal!,
          ),
        ),
      },
    ),
  );
}
