import 'package:flutter/material.dart';

import 'app/starchef_app.dart';
import 'core/config/app_config.dart';
import 'core/network/api_client.dart';
import 'core/storage/session_store.dart';
import 'features/auth/data/auth_repository.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  final repository = AuthRepository(
    apiClient: ApiClient(baseUrl: AppConfig.apiBaseUrl),
    sessionStore: SecureSessionStore(),
  );

  runApp(StarChefApp(authRepository: repository));
}
