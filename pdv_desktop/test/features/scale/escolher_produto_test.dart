import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv_desktop/features/scale/domain/hands_free_machine.dart';
import 'package:starchef_pdv_desktop/features/scale/presentation/escolher_produto_por_quilo_dialog.dart';

ScaleSample amostra(double kg) => ScaleSample(
  weightKg: kg,
  raw: '$kg',
  stable: true,
  at: DateTime(2026, 10, 15, 12),
);

const produtos = [
  {'id': 'buffet', 'name': 'Buffet', 'current_price': '59.90'},
  {'id': 'churrasco', 'name': 'Churrasco', 'current_price': '89.90'},
  {'id': 'doce', 'name': 'Sobremesa', 'current_price': '49.90'},
];

void main() {
  group('máquina', () {
    late HandsFreeMachine machine;
    tearDown(() => machine.dispose());

    HandsFreeMachine iniciar({bool automatica = false}) =>
        machine = HandsFreeMachine(commandTimeout: const Duration(seconds: 30))
          ..start(comandaAutomatica: automatica, escolherProduto: true);

    test('peso estável pergunta o produto antes da comanda', () {
      final efeitos = iniciar().onSample(amostra(0.5), pricePerKg: 0);

      expect(machine.state, HandsFreeState.choosingProduct);
      expect(efeitos, contains(HandsFreeEffect.chooseProduct));
    });

    test('o preço do kg é o do produto escolhido', () {
      iniciar().onSample(amostra(0.5), pricePerKg: 0);

      machine.onProdutoEscolhido(
        productId: 'churrasco',
        pricePerKg: 89.90,
        now: DateTime(2026, 10, 15, 12),
      );

      expect(machine.state, HandsFreeState.waitingCommand);
      expect(machine.weighedItem!.productId, 'churrasco');
      expect(machine.weighedItem!.total, closeTo(44.95, 0.001));
    });

    test('com comanda automática, escolher já lança', () {
      iniciar(automatica: true).onSample(amostra(0.5), pricePerKg: 0);

      final efeitos = machine.onProdutoEscolhido(
        productId: 'buffet',
        pricePerKg: 59.90,
        now: DateTime(2026, 10, 15, 12),
      );

      expect(efeitos, [HandsFreeEffect.launchIntoCommand]);
      expect(machine.state, HandsFreeState.launching);
    });
  });

  group('teclado', () {
    Future<Map<String, dynamic>?> escolherCom(
      WidgetTester tester,
      List<LogicalKeyboardKey> teclas, {
      String? inicial,
    }) async {
      Map<String, dynamic>? escolhido;
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => TextButton(
              onPressed: () async => escolhido = await showDialog(
                context: context,
                builder: (_) => EscolherProdutoPorQuiloDialog(
                  produtos: produtos,
                  pesoKg: 0.5,
                  inicialId: inicial,
                ),
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
      return escolhido;
    }

    testWidgets('abre no último usado: um Enter repete', (tester) async {
      final escolhido = await escolherCom(tester, [
        LogicalKeyboardKey.enter,
      ], inicial: 'churrasco');

      expect(escolhido?['id'], 'churrasco');
    });

    testWidgets('seta para baixo e Enter', (tester) async {
      final escolhido = await escolherCom(tester, [
        LogicalKeyboardKey.arrowDown,
        LogicalKeyboardKey.arrowDown,
        LogicalKeyboardKey.enter,
      ]);

      expect(escolhido?['id'], 'doce');
    });

    testWidgets('número escolhe direto', (tester) async {
      final escolhido = await escolherCom(tester, [LogicalKeyboardKey.digit2]);

      expect(escolhido?['id'], 'churrasco');
    });

    testWidgets('Esc fecha sem escolher', (tester) async {
      final escolhido = await escolherCom(tester, [LogicalKeyboardKey.escape]);

      expect(escolhido, isNull);
      expect(find.byType(EscolherProdutoPorQuiloDialog), findsNothing);
    });
  });
}
