import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/danfe_print_question_dialog.dart';

void main() {
  /// Abre a pergunta e devolve a lista onde cai a resposta ao fechar.
  Future<List<bool>> abrir(WidgetTester tester) async {
    final respostas = <bool>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => respostas.add(
              await DanfePrintQuestionDialog.ask(
                context,
                summary: 'Pedido #7 · NFC-e 12',
              ),
            ),
            child: const Text('concluir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('concluir'));
    await tester.pumpAndSettle();
    expect(find.text('Imprimir a NFC-e?'), findsOneWidget);
    return respostas;
  }

  testWidgets('ENTER imprime', (tester) async {
    final respostas = await abrir(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(respostas, [true]);
  });

  testWidgets('ESC cancela', (tester) async {
    final respostas = await abrir(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(respostas, [false]);
  });

  testWidgets('o botão Cancelar cancela', (tester) async {
    final respostas = await abrir(tester);
    await tester.tap(find.text('Cancelar (Esc)'));
    await tester.pumpAndSettle();
    expect(respostas, [false]);
  });

  testWidgets('clicar fora do modal cancela', (tester) async {
    final respostas = await abrir(tester);
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(respostas, [false]);
  });

  test('só pergunta por nota que a SEFAZ ainda vai autorizar', () {
    expect(danfeOnTheWay({'id': 'n1', 'fiscal_state': 'processing'}), isTrue);
    expect(
      danfeOnTheWay({'id': 'n1', 'fiscal_state': 'awaiting_transmission'}),
      isTrue,
    );
    expect(danfeOnTheWay({'id': 'n1', 'fiscal_state': 'rejected'}), isFalse);
    expect(
      danfeOnTheWay({'id': 'offline-1', 'fiscal_state': 'processing'}),
      isFalse,
    );
  });

  testWidgets('o botão Imprimir imprime', (tester) async {
    final respostas = await abrir(tester);
    await tester.tap(find.text('Imprimir (Enter)'));
    await tester.pumpAndSettle();
    expect(respostas, [true]);
  });
}
