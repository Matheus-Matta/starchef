import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_garcom/core/theme/app_theme.dart';
import 'package:starchef_garcom/core/update/garcom_update_controller.dart';
import 'package:starchef_garcom/features/orders/presentation/update_dialog.dart';

/// O aviso de versão nova deixou de ser uma faixa fina no topo e passou a ser
/// um diálogo na frente de tudo. Este arquivo trava o que essa decisão promete:
/// que ele aparece, que a ação é impossível de não ver, e que ele não prende o
/// garçom no meio do serviço.
void main() {
  Future<GarcomUpdateController> abrir(
    WidgetTester tester, {
    required GarcomUpdateBannerPhase phase,
  }) async {
    final controller = GarcomUpdateController();
    addTearDown(controller.dispose);
    controller.phase = phase;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.materialLight(),
        home: ShadTheme(
          data: AppTheme.shadLight(),
          child: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () => showGarcomUpdateDialog(context, controller),
                  child: const Text('abrir'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    // `pump` com duração, e não `pumpAndSettle`: na fase de download o
    // progresso é indeterminado e gira para sempre — `pumpAndSettle` esperaria
    // uma quietude que nunca chega e estouraria o tempo do teste.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    return controller;
  }

  testWidgets('abre com o recado e um botão de baixar', (tester) async {
    await abrir(tester, phase: GarcomUpdateBannerPhase.available);
    expect(find.text('Nova versão disponível'), findsOneWidget);
    expect(find.text('Baixar e instalar'), findsOneWidget);
  });

  testWidgets('o botão de baixar é maior que um controle comum', (
    tester,
  ) async {
    await abrir(tester, phase: GarcomUpdateBannerPhase.available);
    // A altura é o ponto: o aparelho é operado em pé, com uma mão, e este é o
    // toque que não pode ser confundido com nenhum outro da tela.
    final altura = tester
        .getSize(find.widgetWithText(ShadButton, 'Baixar e instalar'))
        .height;
    expect(altura, greaterThan(AppTheme.controlHeight));
  });

  testWidgets('tocar fora NÃO dispensa o aviso', (tester) async {
    await abrir(tester, phase: GarcomUpdateBannerPhase.available);
    await tester.tapAt(const Offset(8, 8));
    await tester.pumpAndSettle();
    expect(find.text('Nova versão disponível'), findsOneWidget);
  });

  testWidgets('"Agora não" fecha — o garçom nunca fica preso', (tester) async {
    await abrir(tester, phase: GarcomUpdateBannerPhase.available);
    await tester.tap(find.text('Agora não'));
    await tester.pumpAndSettle();
    expect(find.text('Nova versão disponível'), findsNothing);
  });

  testWidgets('enquanto baixa, não dá para sair nem tocar de novo', (
    tester,
  ) async {
    await abrir(tester, phase: GarcomUpdateBannerPhase.downloading);
    expect(find.text('Baixando...'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    // Sair no meio do download deixaria um arquivo parcial e nenhum aviso.
    final sair = tester.widget<TextButton>(
      find.widgetWithText(TextButton, 'Agora não'),
    );
    expect(sair.onPressed, isNull);
  });

  testWidgets('uma falha vira "Tentar de novo", com o motivo', (tester) async {
    final controller = await abrir(
      tester,
      phase: GarcomUpdateBannerPhase.available,
    );
    controller.phase = GarcomUpdateBannerPhase.failed;
    controller.detail = 'Sem espaço no aparelho.';
    controller.notifyListeners();
    await tester.pump();
    expect(find.text('Tentar de novo'), findsOneWidget);
    expect(find.text('Sem espaço no aparelho.'), findsOneWidget);
  });
}
