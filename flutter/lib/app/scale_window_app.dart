import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../core/widgets/app_window_frame.dart';
import '../features/auth/data/auth_repository.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/auth/presentation/login_page.dart';
import '../features/scale/presentation/scale_window_page.dart';

class ScaleWindowApp extends StatefulWidget {
  const ScaleWindowApp({
    super.key,
    required this.authRepository,
    this.preferredRestaurantId,
  });

  final AuthRepository authRepository;
  final String? preferredRestaurantId;

  @override
  State<ScaleWindowApp> createState() => _ScaleWindowAppState();
}

class _ScaleWindowAppState extends State<ScaleWindowApp> {
  late final AuthController _auth = AuthController(widget.authRepository)
    ..initialize();
  ThemeMode _themeMode = ThemeMode.light;

  @override
  void dispose() {
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'StarChef · Balança Rápida',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light(),
    darkTheme: AppTheme.dark(),
    themeMode: _themeMode,
    builder: (context, child) => AppWindowFrame(
      title: 'StarChef · Balança Rápida',
      child: child!,
    ),
    home: ListenableBuilder(
      listenable: _auth,
      builder: (_, _) {
        if (!_auth.initialized) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (!_auth.isAuthenticated) {
          return LoginPage(
            controller: _auth,
            isDark: _themeMode == ThemeMode.dark,
            onToggleTheme: () => setState(() {
              _themeMode = _themeMode == ThemeMode.dark
                  ? ThemeMode.light
                  : ThemeMode.dark;
            }),
          );
        }
        return ScaleWindowPage(
          controller: _auth,
          preferredRestaurantId: widget.preferredRestaurantId,
        );
      },
    ),
  );
}
