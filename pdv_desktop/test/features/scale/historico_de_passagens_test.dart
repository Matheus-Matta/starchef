import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/storage/local_preferences.dart';
import 'package:starchef_pdv_desktop/features/scale/data/historico_de_passagens.dart';
import 'package:starchef_pdv_desktop/features/scale/presentation/historico_de_passagens_dialog.dart';

PassagemDaBalanca passagem(String comanda, {String? job = 'job'}) =>
    PassagemDaBalanca(
      comanda: comanda,
      produto: 'Buffet',
      pesoKg: 0.452,
      total: 31.59,
      quando: DateTime(2026, 10, 15, 12, 3),
      printJobId: job == null ? null : '$job-$comanda',
    );

void main() {
  test('a mais nova primeiro, no máximo 20, e sobrevive a reabrir', () async {
    final pasta = Directory.systemTemp.createTempSync('starchef-hist-');
    addTearDown(() => pasta.deleteSync(recursive: true));
    final arquivo = File('${pasta.path}/preferences.json');
    final historico = HistoricoDePassagens(LocalPreferences(file: arquivo));

    for (var n = 1; n <= 25; n++) {
      await historico.registrar(passagem('$n'));
    }

    final lidas = historico.ler();
    expect(lidas, hasLength(HistoricoDePassagens.maximo));
    expect(lidas.first.comanda, '25');
    expect(lidas.last.comanda, '6');
    expect(lidas.first.printJobId, 'job-25');
  });

  group('teclado do modal', () {
    Future<PassagemDaBalanca?> escolherCom(
      WidgetTester tester,
      List<PassagemDaBalanca> passagens,
      List<LogicalKeyboardKey> teclas,
    ) async {
      PassagemDaBalanca? escolhida;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async => escolhida = await showDialog(
                context: context,
                builder: (_) =>
                    HistoricoDePassagensDialog(passagens: passagens),
              ),
              child: const Text('abrir'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('abrir'));
      await tester.pumpAndSettle();
      for (final tecla in teclas) {
        await tester.sendKeyEvent(tecla);
        await tester.pump();
      }
      await tester.pumpAndSettle();
      return escolhida;
    }

    testWidgets('seta para baixo e Enter reimprime a segunda', (tester) async {
      final escolhida = await escolherCom(
        tester,
        [passagem('17'), passagem('16')],
        [LogicalKeyboardKey.arrowDown, LogicalKeyboardKey.enter],
      );

      expect(escolhida?.comanda, '16');
    });

    testWidgets('passagem sem etiqueta não é reimprimível', (tester) async {
      final escolhida = await escolherCom(
        tester,
        [passagem('17', job: null)],
        [LogicalKeyboardKey.enter],
      );

      expect(escolhida, isNull);
      expect(find.byType(HistoricoDePassagensDialog), findsOneWidget);
    });

    testWidgets('Esc fecha sem reimprimir', (tester) async {
      final escolhida = await escolherCom(
        tester,
        [passagem('17')],
        [LogicalKeyboardKey.escape],
      );

      expect(escolhida, isNull);
      expect(find.byType(HistoricoDePassagensDialog), findsNothing);
    });
  });
}
