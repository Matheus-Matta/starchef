import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:window_manager/window_manager.dart';

import '../core/errors/app_error_host.dart';
import '../core/errors/error_center.dart';
import '../core/storage/local_preferences.dart';
import '../core/theme/app_theme.dart';
import '../core/update/pdv_auto_updater.dart';
import '../core/widgets/app_window_frame.dart';
import '../core/widgets/responsive_scale.dart';
import '../core/widgets/supervisor_close_dialog.dart';
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
    required this.autoUpdater,
  });

  final AuthRepository authRepository;
  final LocalPreferences preferences;
  final ErrorCenter errorCenter;
  final PdvAutoUpdater autoUpdater;

  @override
  State<StarChefApp> createState() => _StarChefAppState();
}

class _StarChefAppState extends State<StarChefApp> with WindowListener {
  final _navigatorKey = GlobalKey<NavigatorState>();
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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(widget.autoUpdater.start(closePdv: _closeForUpdate));
    });
  }

  Future<void> _closeForUpdate() async {
    await windowManager.setPreventClose(false);
    await windowManager.destroy();
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
    final dialogContext = _navigatorKey.currentContext;
    if (_closeDialogOpen || !mounted || dialogContext == null) return;
    _closeDialogOpen = true;
    try {
      // ANTES DO LOGIN O APLICATIVO FECHA DIRETO.
      //
      // Aqui existia uma senha PBKDF2 embutida no binário, igual em toda
      // instalação: um segredo que basta extrair de um executável para valer
      // em todos os terminais. E ela não protegia nada de verdade — impedir o
      // fechamento pela janela não é fronteira de segurança, o processo pode
      // ser encerrado pelo sistema operacional a qualquer momento.
      //
      // Sem sessão não há turno em andamento, caixa aberto nem venda na tela:
      // não há o que proteger. Com sessão, a autorização continua sendo a do
      // restaurante (senha cadastrada ou credencial de administrador), que é
      // configurável por loja e existe justamente para o caso que importa —
      // alguém fechando o PDV no meio do expediente.
      if (!_auth.isAuthenticated) {
        await windowManager.setPreventClose(false);
        await windowManager.destroy();
        return;
      }
      final authorized = await showSupervisorCloseDialog(
        context: dialogContext,
        title: 'Autorização para fechar o PDV',
        description:
            'Use a senha cadastrada do restaurante ou as credenciais de um administrador da conta.',
        confirmLabel: 'Fechar aplicação',
        verifyPassword: _auth.verifySupervisorClosePassword,
        verifyAdminCredentials: _auth.verifyAdministratorCloseCredentials,
        passwordLabel: 'Senha do restaurante',
        invalidPasswordMessage:
            'Senha do restaurante incorreta. Se ela foi alterada, '
            'recarregue os dados do PDV.',
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
    widget.autoUpdater.dispose();
    _auth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    navigatorKey: _navigatorKey,
    title: 'StarChef PDV',
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
            // Em tela cheia não há moldura própria: o conteúdo ocupa também a
            // área da barra de tarefas. Ao sair pelo F11, a moldura volta para
            // oferecer arrastar, minimizar, maximizar e fechar. A barra nunca é
            // escalada, pois usa coordenadas físicas para os controles nativos.
            child: _isFullScreen
                ? ResponsiveScale(
                    child: AppErrorHost(
                      center: widget.errorCenter,
                      child: _withUpdateOverlay(child!),
                    ),
                  )
                : AppWindowFrame(
                    child: ResponsiveScale(
                      child: AppErrorHost(
                        center: widget.errorCenter,
                        child: _withUpdateOverlay(child!),
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
        return _auth.isAuthenticated
            ? HomePage(
                controller: _auth,
                isDark: _themeMode == ThemeMode.dark,
                onToggleTheme: _toggleTheme,
                isFullScreen: _isFullScreen,
                onToggleFullScreen: _toggleFullScreen,
                onClose: onWindowClose,
                preferences: widget.preferences,
              )
            : LoginPage(
                controller: _auth,
                isDark: _themeMode == ThemeMode.dark,
                onToggleTheme: _toggleTheme,
                preferences: widget.preferences,
                onClose: onWindowClose,
              );
      },
    ),
  );

  Widget _withUpdateOverlay(Widget child) => ListenableBuilder(
    listenable: widget.autoUpdater,
    child: child,
    builder: (context, child) {
      if (!widget.autoUpdater.blocksInteraction) return child!;
      final message = switch (widget.autoUpdater.phase) {
        PdvAutoUpdatePhase.downloading => 'Baixando atualização segura…',
        PdvAutoUpdatePhase.preparing => 'Preparando atualização…',
        PdvAutoUpdatePhase.restarting => 'Reiniciando o StarChef…',
        _ => 'Atualizando o StarChef…',
      };
      return Stack(
        fit: StackFit.expand,
        children: [
          child!,
          ColoredBox(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: Center(
              child: SizedBox(
                width: 420,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.system_update_alt, size: 54),
                    const SizedBox(height: 20),
                    Text(
                      message,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 16),
                    LinearProgressIndicator(value: widget.autoUpdater.progress),
                    const SizedBox(height: 12),
                    const Text(
                      'Não desligue o computador. Se a nova versão não abrir, '
                      'a versão anterior será restaurada automaticamente.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      );
    },
  );
}
