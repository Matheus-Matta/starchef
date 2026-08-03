import 'dart:async';

import 'package:flutter/material.dart';

import '../core/errors/app_error_host.dart';
import '../core/errors/error_center.dart';
import '../core/storage/local_preferences.dart';
import '../core/theme/app_theme.dart';
import '../core/widgets/app_window_frame.dart';
import '../core/widgets/responsive_scale.dart';
import '../features/auth/data/auth_repository.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/auth/presentation/login_page.dart';
import '../features/scale/presentation/scale_window_page.dart';

class ScaleWindowApp extends StatefulWidget {
  const ScaleWindowApp({
    super.key,
    required this.authRepository,
    required this.preferences,
    required this.errorCenter,
    this.preferredRestaurantId,
  });

  final AuthRepository authRepository;
  final LocalPreferences preferences;
  final ErrorCenter errorCenter;
  final String? preferredRestaurantId;

  @override
  State<ScaleWindowApp> createState() => _ScaleWindowAppState();
}

class _ScaleWindowAppState extends State<ScaleWindowApp> {
  late final AuthController _auth = AuthController(widget.authRepository)
    ..initialize();
  late ThemeMode _themeMode = widget.preferences.themeMode;

  void _toggleTheme() {
    final next = _themeMode == ThemeMode.dark
        ? ThemeMode.light
        : ThemeMode.dark;
    setState(() => _themeMode = next);
    unawaited(widget.preferences.setThemeMode(next));
  }

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
      // Dentro da moldura para não cobrir os botões da barra de título. A
      // referência é o tamanho padrão desta janela (ver `main.dart`), menor
      // que o do PDV principal — a balança abre numa janela mais compacta.
      child: ResponsiveScale(
        referenceSize: const Size(1180, 760),
        child: AppErrorHost(center: widget.errorCenter, child: child!),
      ),
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
            onToggleTheme: _toggleTheme,
          );
        }
        return ScaleWindowPage(
          controller: _auth,
          preferredRestaurantId: widget.preferredRestaurantId,
          preferences: widget.preferences,
        );
      },
    ),
  );
}
