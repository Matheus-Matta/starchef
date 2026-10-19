import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/danfe_print_question_dialog.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/paid_order_follow_ups.dart';

/// A pergunta do DANFE com os gestos de quem opera um caixa cheio.
void main() {
  test(
    'restaurante que não pergunta: a nota segue sem esperar resposta nenhuma',
    () async {
      Future<bool>? recebida = Future.value(true);
      final emitiu = Completer<void>();

      startPaidOrderFollowUps(
        showNextSale: () {},
        choosePrinter: () async => 'printer-1',
        printReceipt: (_) async {},
        emitInvoice: (_, danfe) async {
          recebida = danfe;
          emitiu.complete();
        },
        refreshCatalog: () async {},
      );

      await emitiu.future;
      expect(recebida, isNull);
    },
  );

  test(
    'caixa que demora a responder não segura a próxima venda nem a nota',
    () async {
      // O cliente seguinte já está no balcão e o modal ficou aberto.
      final resposta = Completer<bool>();
      final eventos = <String>[];

      startPaidOrderFollowUps(
        showNextSale: () => eventos.add('próxima venda'),
        choosePrinter: () async => 'printer-1',
        printReceipt: (_) async => eventos.add('recibo'),
        askDanfe: (_) => resposta.future,
        emitInvoice: (_, _) async => eventos.add('nota'),
        refreshCatalog: () async => eventos.add('catálogo'),
      );
      await Future<void>.delayed(Duration.zero);

      expect(
        eventos,
        containsAll(['próxima venda', 'recibo', 'nota', 'catálogo']),
      );
      expect(resposta.isCompleted, isFalse);
    },
  );

  testWidgets('leitor que manda Enter a mais imprime uma vez só', (
    tester,
  ) async {
    // O leitor de código de barras termina cada leitura com Enter: o caixa
    // bipou o próximo produto com o modal aberto.
    final respostas = <bool>[];
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => respostas.add(
              await DanfePrintQuestionDialog.ask(context, summary: 'Pedido #7'),
            ),
            child: const Text('abrir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(respostas, [true]);
    expect(find.byType(DanfePrintQuestionDialog), findsNothing);
  });
}
