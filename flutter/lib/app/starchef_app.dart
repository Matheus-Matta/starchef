import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:window_manager/window_manager.dart';

import '../core/errors/app_error_host.dart';
import '../core/errors/error_center.dart';
import '../core/storage/local_preferences.dart';
import '../core/theme/app_theme.dart';
import '../core/widgets/app_window_frame.dart';
import '../core/widgets/responsive_scale.dart';
import '../features/auth/data/auth_repository.dart';
import '../features/auth/presentation/auth_controller.dart';
import '../features/auth/presentation/login_page.dart';
import '../features/home/presentation/home_page.dart';

class StarChefApp extends StatefulWidget {
  const StarChefApp({
    super.key,
    required this.authRepository,
    required this.preferences,
    required this.errorCenter,
  });

  final AuthRepository authRepository;
  final LocalPreferences preferences;
  final ErrorCenter errorCenter;

  @override
  State<StarChefApp> createState() => _StarChefAppState();
}

class _StarChefAppState extends State<StarChefApp> {
  late final AuthController _auth = AuthController(widget.authRepository)
    ..initialize();
  late ThemeMode _themeMode = widget.preferences.themeMode;
  // main.dart inicia o PDV principal em tela cheia. Manter o estado alinhado
  // evita o menu oferecer "entrar" em tela cheia quando ele já está nela.
  bool _isFullScreen = true;

  Future<void> _toggleFullScreen() async {
    final current = await windowManager.isFullScreen();
    await windowManager.setFullScreen(!current);
    if (mounted) setState(() => _isFullScreen = !current);
  }

  void _toggleTheme() {
    final next = _themeMode == ThemeMode.dark
        ? ThemeMode.light
        : ThemeMode.dark;
    setState(() => _themeMode = next);
    // O cache local é atualizado na hora; a gravação em disco segue em
    // background porque o tema já está aplicado na interface.
    unawaited(widget.preferences.setThemeMode(next));
  }

  @override
  void dispose() {
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'StarChef PDV',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light(),
    darkTheme: AppTheme.dark(),
    themeMode: _themeMode,
    builder: (context, child) => CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.f11): _toggleFullScreen,
      },
      child: Focus(
        autofocus: true,
        // Em tela cheia não há moldura própria: o conteúdo ocupa também a
        // área da barra de tarefas. Ao sair pelo F11, a moldura volta para
        // oferecer arrastar, minimizar, maximizar e fechar. A barra nunca é
        // escalada, pois usa coordenadas físicas para os controles nativos.
        child: _isFullScreen
            ? ResponsiveScale(
                child: AppErrorHost(center: widget.errorCenter, child: child!),
              )
            : AppWindowFrame(
                child: ResponsiveScale(
                  child: AppErrorHost(
                    center: widget.errorCenter,
                    child: child!,
                  ),
                ),
              ),
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
        return _auth.isAuthenticated
            ? HomePage(
                controller: _auth,
                isDark: _themeMode == ThemeMode.dark,
                onToggleTheme: _toggleTheme,
                isFullScreen: _isFullScreen,
                onToggleFullScreen: _toggleFullScreen,
                preferences: widget.preferences,
              )
            : LoginPage(
                controller: _auth,
                isDark: _themeMode == ThemeMode.dark,
                onToggleTheme: _toggleTheme,
                preferences: widget.preferences,
              );
      },
    ),
  );
}
