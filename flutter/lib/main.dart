import 'package:flutter/material.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:window_manager/window_manager.dart';

import 'app/scale_window_app.dart';
import 'app/starchef_app.dart';
import 'core/config/app_config.dart';
import 'core/errors/error_center.dart';
import 'core/logging/app_logger.dart';
import 'core/network/api_client.dart';
import 'core/storage/local_preferences.dart';
import 'core/storage/session_store.dart';
import 'features/auth/data/auth_repository.dart';
import 'features/cash/data/cash_auth_repository.dart';
import 'features/scale/services/scale_window_launcher.dart';

Future<void> main(List<String> arguments) async {
  WidgetsFlutterBinding.ensureInitialized();
  final scaleWindow = ScaleWindowLauncher.isScaleWindow(arguments);
  final inheritedSession = scaleWindow
      ? await ScaleWindowLauncher.takeSession(arguments)
      : null;
  final preferences = LocalPreferences();
  await preferences.load();
  final config = await AppConfig.load(
    manualOverrideUrl: preferences.apiBaseUrlOverride,
  );
  final errorCenter = ErrorCenter();

  // Erros fora de um handler explícito ainda precisam chegar ao log; nenhum
  // deles pode desaparecer em silêncio durante uma venda.
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    // Sem o widget e a biblioteca, um estouro de layout vira uma linha de log
    // idêntica repetida por item da lista, e não dá para saber onde procurar.
    AppLogger.instance.error(
      'flutter_error',
      data: {
        'library': details.library,
        'context': details.context?.toString(),
        'widget': details.informationCollector == null
            ? null
            : DiagnosticsNode.message(
                details.informationCollector!()
                    .map((node) => node.toString())
                    .join(' | '),
              ).toString(),
      },
      cause: details.exception,
      stackTrace: details.stack,
    );
  };
  AppLogger.instance.info(
    'app_start',
    data: {'mode': scaleWindow ? 'scale_window' : 'pdv'},
  );

  await windowManager.ensureInitialized();
  // As duas janelas validam a Senha do Supervisor antes de encerrar. Sem
  // interceptar o fechamento também na Balança Rápida, o X nativo ignora o
  // diálogo implementado em ScaleWindowApp.
  await windowManager.setPreventClose(true);
  final windowOptions = WindowOptions(
    size: scaleWindow ? const Size(1180, 760) : const Size(1280, 800),
    minimumSize: scaleWindow ? const Size(900, 650) : const Size(960, 640),
    // Tanto o PDV quanto a Balança Rápida iniciam ocupando a tela inteira.
    // O operador ainda pode sair desse modo pelo botão ou por F11.
    fullScreen: true,
    center: true,
    // Uma superfície nativa transparente deixa janelas que estão atrás do
    // PDV vazarem por qualquer pixel ainda não pintado durante resize/escala.
    // O conteúdo Material continua controlando tema claro/escuro depois do
    // primeiro frame; este fundo opaco protege também a inicialização.
    backgroundColor: const Color(0xFF09090B),
    title: scaleWindow ? 'StarChef · Balança Rápida' : 'StarChef PDV',
    titleBarStyle: TitleBarStyle.hidden,
  );
  windowManager.waitUntilReadyToShow(windowOptions, () async {
    await windowManager.show();
    await windowManager.focus();
  });

  final apiClient = ApiClient(baseUrl: config.apiBaseUrl);
  final repository = AuthRepository(
    apiClient: apiClient,
    sessionStore: SecureSessionStore(initialSession: inheritedSession),
    cashAuth: CashAuthRepository(apiClient: apiClient),
  );

  Widget buildApp() => scaleWindow
      ? ScaleWindowApp(
          authRepository: repository,
          preferences: preferences,
          errorCenter: errorCenter,
          preferredRestaurantId: ScaleWindowLauncher.restaurantFrom(arguments),
        )
      : StarChefApp(
          authRepository: repository,
          preferences: preferences,
          errorCenter: errorCenter,
        );

  // Sentry só é inicializado se houver DSN configurada (--dart-define ou
  // .env) — sem ela, comportamento idêntico a hoje, sem overhead.
  final dsn = config.sentryDsn;
  if (dsn != null) {
    await SentryFlutter.init((options) {
      options.dsn = dsn;
      options.environment = scaleWindow ? 'scale_window' : 'pdv';
      options.tracesSampleRate = 0.1;
      options.sendDefaultPii = false;
    }, appRunner: () => runApp(buildApp()));
  } else {
    runApp(buildApp());
  }
}
