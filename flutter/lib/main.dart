import 'package:flutter/material.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:window_manager/window_manager.dart';

import 'app/scale_window_app.dart';
import 'app/starchef_app.dart';
import 'core/config/app_config.dart';
import 'core/errors/app_error.dart';
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
  final preferences = LocalPreferences();
  await preferences.load();
  final config = await AppConfig.load(
    manualOverrideUrl: preferences.apiBaseUrlOverride,
  );
  final errorCenter = ErrorCenter();

  if (config.usedFallbackApiUrl) {
    // Sem --dart-define nem .env, o app "funciona" apontando para
    // localhost:8000 — em um terminal mal instalado isso é silencioso e só
    // aparece como "nada carrega". Torna o problema visível no boot.
    errorCenter.report(
      AppError(
        title: 'URL da API não configurada',
        message:
            'Nenhuma URL de API foi configurada; usando o padrão de '
            'desenvolvimento (${config.apiBaseUrl}).',
        origin: AppErrorOrigin.application,
        severity: AppErrorSeverity.warning,
        recommendedAction:
            'Configure API_BASE_URL (--dart-define ou .env) antes de usar '
            'este terminal em produção.',
        dedupeKey: 'api-url-fallback',
      ),
    );
  }

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
  final windowOptions = WindowOptions(
    size: scaleWindow ? const Size(1180, 760) : const Size(1280, 800),
    minimumSize: scaleWindow ? const Size(900, 650) : const Size(960, 640),
    center: true,
    backgroundColor: Colors.transparent,
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
    sessionStore: SecureSessionStore(),
    cashAuth: CashAuthRepository(apiClient: apiClient),
  );

  Widget buildApp() => scaleWindow
      ? ScaleWindowApp(
          authRepository: repository,
          preferences: preferences,
          errorCenter: errorCenter,
          preferredRestaurantId: ScaleWindowLauncher.restaurantFrom(
            arguments,
          ),
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
