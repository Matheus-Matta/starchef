import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error_host.dart';
import 'package:starchef_pdv_desktop/core/errors/error_center.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/core/widgets/app_dialog.dart';
import 'package:starchef_pdv_desktop/core/widgets/app_window_frame.dart';
import 'package:starchef_pdv_desktop/core/widgets/responsive_scale.dart';

/// A árvore real do aplicativo, e o que acontece quando um alerta aparece.
///
/// `ResponsiveScale` é um `LayoutBuilder`: ele constrói o filho durante o
/// LAYOUT, e por isso a subárvore inteira — Navigator, diálogos, o Overlay dos
/// alertas — vive num **escopo de build próprio**. Marcar um widget desse
/// escopo como sujo fora de um quadro é o que produz, no terminal:
///
///   Tried to build dirty widget in the wrong build scope.
///   The root of the build scope was: LayoutBuilder
///   The offending element ... was: AnimatedBuilder
///
/// seguido de `'debugNeedsLayout': is not true`.
///
/// Estes cenários NÃO reproduzem esse erro — e é por isso que eles ficam:
/// cada um descarta uma hipótese e, junto, eles guardam um arranjo
/// reconhecidamente frágil (o app inteiro construído dentro de um callback
/// de layout). Se um dia um deles passar a falhar, o gatilho foi achado.
void main() {
  /// Monta exatamente o que `StarChefApp.build` monta, na mesma ordem.
  Widget montarArvoreDoApp(
    ErrorCenter center, {
    required Widget home,
    required GlobalKey<NavigatorState> navigatorKey,
  }) => MaterialApp(
    navigatorKey: navigatorKey,
    theme: AppTheme.light(),
    debugShowCheckedModeBanner: false,
    builder: (context, child) => ColoredBox(
      color: Theme.of(context).scaffoldBackgroundColor,
      child: ShadTheme(
        data: AppTheme.shadLight(),
        child: CallbackShortcuts(
          bindings: {const SingleActivator(LogicalKeyboardKey.f11): () {}},
          child: Focus(
            autofocus: true,
            child: ResponsiveScale(
              child: AppErrorHost(center: center, child: child!),
            ),
          ),
        ),
      ),
    ),
    home: home,
  );

  Future<void> comJanelaDePdv(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
  }

  testWidgets('alerta reportado fora de um quadro não quebra o layout', (
    tester,
  ) async {
    // É o caso real: a falha chega de uma resposta da API — ou seja, de um
    // `await`, entre quadros — e o cartão de erro precisa aparecer.
    await comJanelaDePdv(tester);
    final center = ErrorCenter();
    addTearDown(center.dispose);

    await tester.pumpWidget(
      montarArvoreDoApp(
        center,
        navigatorKey: GlobalKey<NavigatorState>(),
        home: const Scaffold(body: Center(child: Text('pdv'))),
      ),
    );

    // O corpo do teste já roda ENTRE quadros — é o mesmo lugar de onde uma
    // resposta da API chega. Um `Future.delayed` aqui só travaria o relógio
    // falso do teste.
    center.report(
      AppError(
        title: 'O comprovante não saiu na impressora',
        message: 'Rota ou registro não encontrado.',
        severity: AppErrorSeverity.failure,
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('O comprovante não saiu na impressora'), findsOneWidget);

    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  });

  testWidgets('fechar o diálogo e alertar entre quadros', (tester) async {
    // A sequência exata do suprimento: autoriza, fecha o diálogo, e só depois
    // — num `await` seguinte — a impressão do comprovante falha e alerta.
    await comJanelaDePdv(tester);
    final center = ErrorCenter();
    addTearDown(center.dispose);
    final senha = TextEditingController();
    addTearDown(senha.dispose);

    await tester.pumpWidget(
      montarArvoreDoApp(
        center,
        navigatorKey: GlobalKey<NavigatorState>(),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  await showDialog<void>(
                    context: context,
                    builder: (dialogContext) => AppDialog(
                      title: const Text('Autorizar suprimento'),
                      content: SizedBox(
                        width: 420,
                        child: TextField(controller: senha, obscureText: true),
                      ),
                      actions: [
                        FilledButton(
                          onPressed: () => Navigator.pop(dialogContext),
                          child: const Text('Autorizar'),
                        ),
                      ],
                    ),
                  );
                  // Depois do diálogo: recarrega e imprime. A impressão falha.
                  await Future<void>.delayed(Duration.zero);
                  if (!context.mounted) return;
                  ErrorCenterScope.read(context).report(
                    AppError(
                      title: 'O comprovante não saiu na impressora',
                      message: 'Rota ou registro não encontrado.',
                      severity: AppErrorSeverity.failure,
                    ),
                  );
                },
                child: const Text('abrir'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Autorizar'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('O comprovante não saiu na impressora'), findsOneWidget);

    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  });

  testWidgets('a janela muda de tamanho enquanto o alerta está na tela', (
    tester,
  ) async {
    // O `LayoutBuilder` reconstrói a subárvore a cada mudança de restrição.
    // Com um alerta vivo (um `ListenableBuilder` sujo) no Overlay, é aqui que
    // o escopo de build errado apareceria.
    await comJanelaDePdv(tester);
    final center = ErrorCenter();
    addTearDown(center.dispose);

    await tester.pumpWidget(
      montarArvoreDoApp(
        center,
        navigatorKey: GlobalKey<NavigatorState>(),
        home: const Scaffold(body: Center(child: Text('pdv'))),
      ),
    );

    center.report(
      AppError(
        title: 'Sem conexão com o servidor',
        message: 'Nada foi registrado.',
        severity: AppErrorSeverity.failure,
      ),
    );
    await tester.pump();

    tester.view.physicalSize = const Size(900, 640);
    await tester.pump();
    tester.view.physicalSize = const Size(1440, 900);
    await tester.pump();

    expect(tester.takeException(), isNull);

    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  });

  testWidgets('F11 com um alerta na tela não quebra o escopo de build', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final center = ErrorCenter();
    addTearDown(center.dispose);
    final navigatorKey = GlobalKey<NavigatorState>();
    var telaCheia = true;
    late StateSetter alternar;

    Widget conteudo(Widget child) =>
        AppErrorHost(center: center, child: child);

    await tester.pumpWidget(
      StatefulBuilder(
        builder: (context, setState) {
          alternar = setState;
          return MaterialApp(
            navigatorKey: navigatorKey,
            theme: AppTheme.light(),
            debugShowCheckedModeBanner: false,
            builder: (context, child) => ColoredBox(
              color: Theme.of(context).scaffoldBackgroundColor,
              child: ShadTheme(
                data: AppTheme.shadLight(),
                child: Focus(
                  autofocus: true,
                  child: telaCheia
                      ? ResponsiveScale(child: conteudo(child!))
                      : AppWindowFrame(
                          child: ResponsiveScale(child: conteudo(child!)),
                        ),
                ),
              ),
            ),
            home: const Scaffold(body: Center(child: Text('pdv'))),
          );
        },
      ),
    );

    // Um alerta vivo: é ele que mantém um `ListenableBuilder` escutando e
    // sujo enquanto a árvore troca de forma.
    center.report(
      AppError(
        title: 'O comprovante não saiu na impressora',
        message: 'Rota ou registro não encontrado.',
        severity: AppErrorSeverity.failure,
      ),
    );
    await tester.pump();
    expect(find.text('O comprovante não saiu na impressora'), findsOneWidget);

    // Sai da tela cheia: a subárvore com GlobalKey muda de LayoutBuilder.
    alternar(() => telaCheia = false);
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'ao sair da tela cheia');

    // E volta.
    alternar(() => telaCheia = true);
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'ao voltar para tela cheia');

    // Um alerta novo logo depois da troca, que é quando o escopo recém-criado
    // ainda está se acertando.
    center.report(
      AppError(
        title: 'Sem conexão com o servidor',
        message: 'Nada foi registrado.',
        severity: AppErrorSeverity.failure,
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'alerta após a troca');

    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  });

  testWidgets('tooltip aberto + alerta + janela mudando de tamanho', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final center = ErrorCenter();
    addTearDown(center.dispose);

    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        debugShowCheckedModeBanner: false,
        builder: (context, child) => ColoredBox(
          color: Theme.of(context).scaffoldBackgroundColor,
          child: ShadTheme(
            data: AppTheme.shadLight(),
            child: Focus(
              autofocus: true,
              child: ResponsiveScale(
                child: AppErrorHost(center: center, child: child!),
              ),
            ),
          ),
        ),
        home: const Scaffold(
          body: Center(
            child: Tooltip(
              message: 'Conectado ao servidor.',
              child: Icon(Icons.cloud_done_outlined, size: 40),
            ),
          ),
        ),
      ),
    );

    // O mouse para em cima do indicador — o balão abre no Overlay.
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    addTearDown(mouse.removePointer);
    await mouse.addPointer(location: Offset.zero);
    await tester.pump();
    await mouse.moveTo(tester.getCenter(find.byType(Tooltip)));
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('Conectado ao servidor.'), findsOneWidget);

    // Com o balão aberto: chega o alerta de erro...
    center.report(
      AppError(
        title: 'O comprovante não saiu na impressora',
        message: 'Rota ou registro não encontrado.',
        severity: AppErrorSeverity.failure,
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'alerta com tooltip aberto');

    // ...e a janela muda de tamanho, refazendo o layout do LayoutBuilder.
    tester.view.physicalSize = const Size(1000, 700);
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'resize com tooltip aberto');

    tester.view.physicalSize = const Size(1440, 900);
    await tester.pump();
    expect(tester.takeException(), isNull, reason: 'segundo resize');

    await mouse.moveTo(const Offset(5, 5));
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'ao fechar o balão');
  });
}
