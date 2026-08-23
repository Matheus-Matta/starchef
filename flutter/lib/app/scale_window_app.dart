import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:window_manager/window_manager.dart';

import '../core/errors/app_error_host.dart';
import '../core/errors/error_center.dart';
import '../core/storage/local_preferences.dart';
import '../core/theme/app_theme.dart';
import '../core/widgets/app_window_frame.dart';
import '../core/widgets/responsive_scale.dart';
import '../core/widgets/supervisor_close_dialog.dart';
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

class _ScaleWindowAppState extends State<ScaleWindowApp> with WindowListener {
  final _navigatorKey = GlobalKey<NavigatorState>();
  late final AuthController _auth = AuthController(widget.authRepository)
    ..initialize();
  late ThemeMode _themeMode = widget.preferences.themeMode;
  // main.dart inicia também a Balança Rápida em tela cheia.
  bool _isFullScreen = true;
  bool _closeDialogOpen = false;

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);
  }

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
    unawaited(widget.preferences.setThemeMode(next));
  }

  Future<void> _requestClose() => onWindowClose();

  @override
  Future<void> onWindowClose() async {
    final dialogContext = _navigatorKey.currentContext;
    if (_closeDialogOpen || !mounted || dialogContext == null) return;
    _closeDialogOpen = true;
    try {
      final authorized = await showSupervisorCloseDialog(
        context: dialogContext,
        title: 'Fechar a Balança Rápida',
        description:
            'Informe a Senha do Supervisor para encerrar esta estação.',
        confirmLabel: 'Fechar balança',
        verifyPassword: _auth.verifySupervisorClosePassword,
        onInvalidPassword: () async {
          await windowManager.setFullScreen(true);
          if (mounted) setState(() => _isFullScreen = true);
        },
      );
      if (authorized) {
        await windowManager.setPreventClose(false);
        await windowManager.destroy();
      }
    } finally {
      _closeDialogOpen = false;
    }
  }

  @override
  void dispose() {
    windowManager.removeListener(this);
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: _navigatorKey,
    title: 'StarChef · Balança Rápida',
    debugShowCheckedModeBanner: false,
    theme: AppTheme.light(),
    darkTheme: AppTheme.dark(),
    themeMode: _themeMode,
    builder: (context, child) => ColoredBox(
      color: Theme.of(context).scaffoldBackgroundColor,
      child: ShadTheme(
        data: Theme.of(context).brightness == Brightness.dark
            ? AppTheme.shadDark()
            : AppTheme.shadLight(),
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.f11): _toggleFullScreen,
          },
          child: Focus(
            autofocus: true,
            child: _isFullScreen
                ? ResponsiveScale(
                    referenceSize: const Size(1180, 760),
                    child: AppErrorHost(
                      center: widget.errorCenter,
                      child: child!,
                    ),
                  )
                : AppWindowFrame(
                    title: 'StarChef · Balança Rápida',
                    child: ResponsiveScale(
                      referenceSize: const Size(1180, 760),
                      child: AppErrorHost(
                        center: widget.errorCenter,
                        child: child!,
                      ),
                    ),
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
        if (!_auth.isAuthenticated) {
          return LoginPage(
            controller: _auth,
            isDark: _themeMode == ThemeMode.dark,
            onToggleTheme: _toggleTheme,
            preferences: widget.preferences,
            onClose: _requestClose,
          );
        }
        return ScaleWindowPage(
          controller: _auth,
          preferredRestaurantId: widget.preferredRestaurantId,
          preferences: widget.preferences,
          isFullScreen: _isFullScreen,
          onToggleFullScreen: _toggleFullScreen,
          onClose: _requestClose,
        );
      },
    ),
  );
}
