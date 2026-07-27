import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'app/scale_window_app.dart';
import 'app/starchef_app.dart';
import 'core/config/app_config.dart';
import 'core/network/api_client.dart';
import 'core/storage/session_store.dart';
import 'features/auth/data/auth_repository.dart';
import 'features/cash/data/cash_auth_repository.dart';
import 'features/scale/services/scale_window_launcher.dart';

Future<void> main(List<String> arguments) async {
  WidgetsFlutterBinding.ensureInitialized();
  final config = await AppConfig.load();
  final scaleWindow = ScaleWindowLauncher.isScaleWindow(arguments);

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

  runApp(
    scaleWindow
        ? ScaleWindowApp(
            authRepository: repository,
            preferredRestaurantId: ScaleWindowLauncher.restaurantFrom(
              arguments,
            ),
          )
        : StarChefApp(authRepository: repository),
  );
}
