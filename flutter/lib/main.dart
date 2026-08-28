import 'dart:async';

import 'package:flutter/material.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:wakelock_plus/wakelock_plus.dart';
import 'package:window_manager/window_manager.dart';

import 'app/scale_window_app.dart';
import 'app/starchef_app.dart';
import 'core/config/app_config.dart';
import 'core/errors/app_error.dart';
import 'core/errors/error_center.dart';
import 'core/logging/app_logger.dart';
import 'core/network/api_client.dart';
import 'core/storage/app_paths.dart';
import 'core/storage/local_preferences.dart';
import 'core/storage/session_store.dart';
import 'core/update/pdv_auto_updater.dart';
import 'features/auth/data/auth_repository.dart';
import 'features/cash/data/cash_auth_repository.dart';
import 'features/scale/services/scale_window_launcher.dart';

Future<void> main(List<String> arguments) async {
  WidgetsFlutterBinding.ensureInitialized();
  // Um caixa (ou o Caixa Principal, que retransmite pedidos do app do
  // garçom pela rede local) nunca pode ir para suspensão: no Linux, o
  // gerenciamento de energia da tela/Wi-Fi desktop costuma suspender o
  // processo e a conexão de rede quando ninguém toca no terminal, e a
  // impressão automática só retomava quando alguém mexia na tela de novo.
  unawaited(WakelockPlus.enable());
  final scaleWindow = ScaleWindowLauncher.isScaleWindow(arguments);
  final inheritedSession = scaleWindow
      ? await ScaleWindowLauncher.takeSession(arguments)
      : null;
  final errorCenter = ErrorCenter();
  try {
    await AppPaths.verifyPersistentStorage();
  } catch (error, stackTrace) {
    errorCenter.report(
      AppError(
        title: 'Armazenamento local sem permissão',
        message:
            'O PDV não consegue gravar seus dados permanentes. Login, fila '
            'offline e pareamento do Caixa Principal podem ser perdidos ao '
            'fechar o aplicativo.',
        severity: AppErrorSeverity.failure,
        recommendedAction:
            'Abra o PDV sempre com o mesmo usuário, sem sudo, e corrija o '
            'proprietário da pasta local indicada nos detalhes.',
        technicalDetails:
            'Diretório: ${AppPaths.dataDirectory().path}\n$error\n$stackTrace',
        dedupeKey: 'persistent-storage-unavailable',
      ),
    );
  }
  final preferences = LocalPreferences();
  await preferences.load();
  final config = await AppConfig.load(
    manualOverrideUrl: preferences.apiBaseUrlOverride,
  );
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
    // No Linux, o WM às vezes ignora `fullScreen` passado na criação da
    // janela (aplica só depois de mapeada) — sem isto, a Balança Rápida abria
    // como uma janela pequena flutuando sobre o PDV, deixando sidebar e
    // header do PDV visíveis ao redor dela.
    await windowManager.setFullScreen(true);
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
          autoUpdater: PdvAutoUpdater(),
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
