import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import 'core/config/app_env.dart';
import 'core/network/api_client.dart';
import 'core/relay/principal_client.dart';
import 'core/relay/relay_gateway.dart';
import 'core/storage/offline_queue_store.dart';
import 'core/storage/principal_cache.dart';
import 'core/storage/session_store.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/presentation/login_page.dart';
import 'features/auth/presentation/principal_setup_page.dart';
import 'features/auth/presentation/session_controller.dart';
import 'features/orders/data/order_drafts.dart';
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

  /// Vive fora do [OrdersRepository] de propósito: o repositório é
  /// reconstruído a cada mudança de sessão/pareamento, mas a fila de
  /// pendências tem que sobreviver a essas trocas — e a fechar e abrir o app.
  late final RelayGateway _gateway;

  /// Pelo mesmo motivo: o cache das últimas leituras confirmadas pelo Caixa
  /// Principal precisa ser um só. Duas instâncias sobre o mesmo arquivo
  /// divergiriam em memória e uma sobrescreveria o que a outra guardou.
  late final PrincipalCache _cache;

  /// Pelo mesmo motivo dos dois acima: os itens escolhidos e ainda não
  /// enviados não podem se perder quando o repositório é reconstruído — nem
  /// quando o garçom fecha o app no meio do salão.
  late final OrderDrafts _drafts;

  @override
  void initState() {
    super.initState();
    _api = ApiClient(baseUrl: AppEnv.backendUrl);
    _principal = PrincipalClient();
    _gateway = RelayGateway(client: _principal, store: OfflineQueueStore());
    _cache = PrincipalCache();
    _drafts = OrderDrafts();
    _controller = SessionController(
      api: _api,
      principalClient: _principal,
      store: SecureSessionStore(),
      cache: _cache,
    );
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    // Ordem importa: a fila é lida antes da sessão, para que — se havia
    // pendências de uma sessão anterior — o gateway já esteja pronto assim
    // que `updateContext` chegar com a sessão/pareamento restaurados.
    await _gateway.restore();
    await _drafts.restore();
    await _controller.restore();
    _syncGatewayContext();
    _controller.addListener(_syncGatewayContext);
  }

  /// Mantém o alvo do reenvio em dia: se a fila tentasse contra uma sessão ou
  /// um caixa que não existem mais, todo reenvio falharia silenciosamente.
  void _syncGatewayContext() {
    final session = _controller.session;
    final principal = _controller.principal;
    if (session != null && principal != null) {
      _gateway.updateContext(config: principal, identity: session.identity);
    }
  }

  @override
  void dispose() {
    _controller.removeListener(_syncGatewayContext);
    _controller.dispose();
    _gateway.dispose();
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
            principalClient: _principal,
            gateway: _gateway,
            session: _controller.session!,
            principal: _controller.principal!,
            cache: _cache,
            drafts: _drafts,
          ),
        ),
      },
    ),
  );
}
