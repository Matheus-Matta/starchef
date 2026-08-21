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

class _StarChefAppState extends State<StarChefApp> with WindowListener {
  late final AuthController _auth = AuthController(widget.authRepository)
    ..initialize();
  late ThemeMode _themeMode = widget.preferences.themeMode;
  // main.dart inicia o PDV principal em tela cheia. Manter o estado alinhado
  // evita o menu oferecer "entrar" em tela cheia quando ele já está nela.
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
    // O cache local é atualizado na hora; a gravação em disco segue em
    // background porque o tema já está aplicado na interface.
    unawaited(widget.preferences.setThemeMode(next));
  }

  @override
  Future<void> onWindowClose() async {
    if (_closeDialogOpen || !mounted) return;
    _closeDialogOpen = true;
    final password = TextEditingController();
    String? errorMessage;
    var checking = false;
    try {
      final authorized = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, update) {
            Future<void> confirm() async {
              if (checking || password.text.isEmpty) return;
              update(() {
                checking = true;
                errorMessage = null;
              });
              final valid = await _auth.verifySupervisorClosePassword(
                password.text,
              );
              if (!dialogContext.mounted) return;
              if (valid) {
                Navigator.pop(dialogContext, true);
                return;
              }
              await windowManager.setFullScreen(true);
              if (mounted) setState(() => _isFullScreen = true);
              update(() {
                checking = false;
                errorMessage = 'Senha do Supervisor incorreta.';
                password.clear();
              });
            }

            return AlertDialog(
              title: const Row(
                children: [
                  Icon(Icons.admin_panel_settings_outlined),
                  SizedBox(width: 10),
                  Expanded(child: Text('Autorização para fechar o PDV')),
                ],
              ),
              content: SizedBox(
                width: 420,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Informe a Senha do Supervisor cadastrada para o restaurante.',
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: password,
                      autofocus: true,
                      obscureText: true,
                      enabled: !checking,
                      decoration: InputDecoration(
                        labelText: 'Senha do Supervisor',
                        prefixIcon: const Icon(Icons.lock_outline),
                        errorText: errorMessage,
                      ),
                      onSubmitted: (_) => unawaited(confirm()),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: checking
                      ? null
                      : () => Navigator.pop(dialogContext, false),
                  child: const Text('Manter PDV aberto'),
                ),
                FilledButton.icon(
                  onPressed: checking ? null : () => unawaited(confirm()),
                  icon: checking
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.power_settings_new),
                  label: const Text('Fechar aplicação'),
                ),
              ],
            );
          },
        ),
      );
      if (authorized == true) {
        await windowManager.setPreventClose(false);
        await windowManager.destroy();
      }
    } finally {
      password.dispose();
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
