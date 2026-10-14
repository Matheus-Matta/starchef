import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/calculo_do_total.dart';

/// Cupom, desconto, taxa e CPF/CNPJ mudam o total — e quem decide o total é o
/// servidor. Enquanto ele não responde, o caixa NÃO pode registrar pagamento
/// nem concluir sobre o total antigo.
void main() {
  group('CalculoDoTotal', () {
    test('resposta atrasada mantem o calculo em curso', () async {
      final calculo = CalculoDoTotal();
      final resposta = Completer<int>();
      final rodando = calculo.rodar<int>(
        calcular: () => resposta.future,
        aplicar: (_) {},
        falhar: (_) {},
      );

      await Future<void>.delayed(Duration.zero);
      expect(calculo.emCurso, isTrue);

      resposta.complete(1);
      await rodando;
      expect(calculo.emCurso, isFalse);
    });

    test('sucesso aplica e libera', () async {
      final calculo = CalculoDoTotal();
      int? aplicado;
      await calculo.rodar<int>(
        calcular: () async => 42,
        aplicar: (valor) => aplicado = valor,
        falhar: (_) {},
      );

      expect(aplicado, 42);
      expect(calculo.emCurso, isFalse);
    });

    test('erro libera sem aplicar o total errado', () async {
      final calculo = CalculoDoTotal();
      var aplicou = false;
      Object? erro;
      await calculo.rodar<int>(
        calcular: () async => throw StateError('recusado'),
        aplicar: (_) => aplicou = true,
        falhar: (falha) => erro = falha,
      );

      expect(aplicou, isFalse);
      expect(erro, isA<StateError>());
      expect(calculo.emCurso, isFalse);
    });

    test('duplo clique nao dispara um segundo calculo', () async {
      final calculo = CalculoDoTotal();
      final resposta = Completer<int>();
      var chamadas = 0;
      Future<int> calcular() {
        chamadas++;
        return resposta.future;
      }

      final primeiro = calculo.rodar<int>(
        calcular: calcular,
        aplicar: (_) {},
        falhar: (_) {},
      );
      final segundo = await calculo.rodar<int>(
        calcular: calcular,
        aplicar: (_) {},
        falhar: (_) {},
      );

      expect(segundo, isFalse);
      expect(chamadas, 1);
      resposta.complete(1);
      expect(await primeiro, isTrue);
    });

    test('resposta antiga nao sobrescreve a mais recente', () async {
      // O caixa saiu do pagamento e voltou com outro cupom: a resposta do
      // primeiro chega depois e não pode trocar o total do segundo.
      final calculo = CalculoDoTotal();
      final antiga = Completer<String>();
      final aplicados = <String>[];
      final primeiro = calculo.rodar<String>(
        calcular: () => antiga.future,
        aplicar: aplicados.add,
        falhar: (_) {},
      );

      calculo.descartar();
      await calculo.rodar<String>(
        calcular: () async => 'NOVO',
        aplicar: aplicados.add,
        falhar: (_) {},
      );
      antiga.complete('VELHO');

      expect(await primeiro, isFalse);
      expect(aplicados, ['NOVO']);
      expect(calculo.emCurso, isFalse);
    });

    test('o erro de uma resposta antiga nao aparece', () async {
      final calculo = CalculoDoTotal();
      final antiga = Completer<int>();
      Object? erro;
      final primeiro = calculo.rodar<int>(
        calcular: () => antiga.future,
        aplicar: (_) {},
        falhar: (falha) => erro = falha,
      );

      calculo.descartar();
      antiga.completeError(StateError('velho'));
      await primeiro;

      expect(erro, isNull);
    });
  });

  group('BotaoDoPagamento', () {
    Future<void> montar(
      WidgetTester tester, {
      required bool calculando,
      required VoidCallback onPressed,
    }) => tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 240,
            child: BotaoDoPagamento(
              calculando: calculando,
              icon: Icons.add_card,
              label: 'Adicionar pagamento',
              onPressed: onPressed,
            ),
          ),
        ),
      ),
    );

    testWidgets('calculando, diz Calculando total e nao aceita clique', (
      tester,
    ) async {
      var cliques = 0;
      await montar(tester, calculando: true, onPressed: () => cliques++);

      expect(find.text('Calculando total...'), findsOneWidget);
      expect(find.text('Adicionar pagamento'), findsNothing);
      await tester.tap(find.byType(BotaoDoPagamento));
      expect(cliques, 0);
    });

    testWidgets('pronto, mostra o rotulo e aceita o clique', (tester) async {
      var cliques = 0;
      await montar(tester, calculando: false, onPressed: () => cliques++);

      await tester.tap(find.text('Adicionar pagamento'));
      expect(cliques, 1);
    });
  });
}
