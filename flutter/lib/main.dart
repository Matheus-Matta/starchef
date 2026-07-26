import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

import 'app/starchef_app.dart';
import 'core/config/app_config.dart';
import 'core/network/api_client.dart';
import 'core/storage/session_store.dart';
import 'features/auth/data/auth_repository.dart';
import 'features/cash/data/cash_auth_repository.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final config = await AppConfig.load();

  await windowManager.ensureInitialized();
  const windowOptions = WindowOptions(
    size: Size(1280, 800),
    minimumSize: Size(960, 640),
    center: true,
    backgroundColor: Colors.transparent,
    title: 'StarChef PDV',
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

  runApp(StarChefApp(authRepository: repository));
}
