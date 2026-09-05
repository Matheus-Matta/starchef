import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/widgets/responsive_scale.dart';

void main() {
  Future<double> reportedScale(WidgetTester tester, Size physicalSize) async {
    late double scale;
    tester.view.physicalSize = physicalSize;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        home: ResponsiveScale(
          child: Builder(
            builder: (context) {
              final virtualWidth = MediaQuery.sizeOf(context).width;
              scale = physicalSize.width / virtualWidth;
              return const SizedBox();
            },
          ),
        ),
      ),
    );
    return scale;
  }

  group('cálculo da escala', () {
    testWidgets('no tamanho de referência a escala é 1', (tester) async {
      final scale = await reportedScale(tester, const Size(1280, 800));
      expect(scale, closeTo(1.0, 0.001));
    });

    testWidgets('janela menor que a referência encolhe (zoom out)', (
      tester,
    ) async {
      // 1180/1280 = 0,92: encolhe, e ainda acima do piso.
      final scale = await reportedScale(tester, const Size(1180, 800));
      expect(scale, closeTo(1180 / 1280, 0.001));
    });

    testWidgets('a dimensão mais apertada decide a escala', (tester) async {
      // Larga e baixa: a altura é o fator limitante.
      final scale = await reportedScale(tester, const Size(2000, 760));
      expect(scale, closeTo(760 / 800, 0.001));
    });

    testWidgets('numa janela apertada a escala acompanha, sem travar', (
      tester,
    ) async {
      // 960/1280 = 0,75 e 640/800 = 0,8: vale o mais apertado, 0,75 — acima do
      // piso, então a conta passa inteira. Já foi travado em 0,9 aqui, e o
      // efeito era o operador diminuir a janela e nada mudar de tamanho.
      final scale = await reportedScale(tester, const Size(960, 640));
      expect(scale, closeTo(0.75, 0.001));
    });

    testWidgets('janela muito grande não ultrapassa o teto', (tester) async {
      final scale = await reportedScale(tester, const Size(3840, 2160));
      expect(scale, lessThanOrEqualTo(1.3));
    });

    testWidgets('janela muito pequena não ultrapassa o piso', (tester) async {
      final scale = await reportedScale(tester, const Size(400, 300));
      expect(scale, greaterThanOrEqualTo(0.72));
    });
  });

  group('espaço já consumido por um ancestral', () {
    // Reproduz a estrutura real do app: `AppWindowFrame` desenha uma barra
    // de título de 38px acima do conteúdo, numa Column. Antes desta
    // correção, o ResponsiveScale usava o tamanho da janela inteira (via
    // `MediaQuery`) em vez do espaço que sobrava depois da barra — o
    // conteúdo era desenhado maior do que o espaço real e a borda
    // direita/inferior saía cortada da tela. Este teste prende esse
    // comportamento: o espaço "virtual" reportado ao filho tem que refletir
    // só o que sobrou, nunca a janela inteira.
    testWidgets(
      'a escala considera o espaço restante, não o tamanho da janela',
      (tester) async {
        const windowSize = Size(1920, 1080);
        const titleBarHeight = 38.0;
        late Size reportedVirtualSize;

        tester.view.physicalSize = windowSize;
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);

        await tester.pumpWidget(
          MaterialApp(
            home: Column(
              children: [
                const SizedBox(height: titleBarHeight),
                Expanded(
                  child: ResponsiveScale(
                    child: Builder(
                      builder: (context) {
                        reportedVirtualSize = MediaQuery.sizeOf(context);
                        return const SizedBox.expand();
                      },
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Nada pode estourar: nem a Column externa, nem o FittedBox interno.
        expect(tester.takeException(), isNull);

        // A altura disponível de verdade é a da janela menos a barra —
        // 1042px, não 1080px. Se o cálculo ainda usasse a janela inteira, a
        // escala por altura sairia de 1080/800 em vez de 1042/800, e o
        // tamanho virtual reportado aqui seria outro.
        final availableHeight = windowSize.height - titleBarHeight;
        final expectedScale = math.min(
          windowSize.width / 1280,
          availableHeight / 800,
        ).clamp(0.72, 1.3);
        expect(
          reportedVirtualSize.height,
          closeTo(availableHeight / expectedScale, 0.5),
        );
      },
    );
  });
}
