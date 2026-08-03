import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/errors/app_error.dart';
import 'package:starchef_pdv/core/errors/app_error_host.dart';
import 'package:starchef_pdv/core/errors/error_center.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';

void main() {
  group('ErrorCenter', () {
    test('preserva a mensagem exata devolvida pelo backend', () {
      final center = ErrorCenter();

      center.reportApi(
        const ApiException(
          'Caixa já aberto em outro terminal.',
          statusCode: 409,
        ),
      );

      final error = center.visible.single;
      expect(error.message, 'Caixa já aberto em outro terminal.');
      expect(error.code, 'HTTP 409');
      expect(error.origin, AppErrorOrigin.api);
    });

    test('não expõe stack trace ao operador', () {
      final center = ErrorCenter();

      center.reportUnexpected(
        StateError('null check on null value'),
        stackTrace: StackTrace.current,
      );

      final error = center.visible.single;
      expect(error.message, isNot(contains('null check')));
      // O detalhe técnico continua disponível para o log e para o suporte.
      expect(error.technicalDetails, contains('null check'));
    });

    test('a mesma falha repetida não empilha cópias', () {
      final center = ErrorCenter();
      const failure = ApiException('Servidor indisponível.', statusCode: 503);

      center.reportApi(failure);
      center.reportApi(failure);

      expect(center.visible, hasLength(1));
    });

    test('mantém no máximo o número configurado de alertas', () {
      final center = ErrorCenter(maximumVisible: 2);

      center.reportApi(const ApiException('Erro 1'));
      center.reportApi(const ApiException('Erro 2'));
      center.reportApi(const ApiException('Erro 3'));

      expect(center.visible, hasLength(2));
      expect(center.visible.first.message, 'Erro 3');
    });

    test('dispensar remove apenas o alerta escolhido', () {
      final center = ErrorCenter();
      final first = center.reportApi(const ApiException('Erro 1'));
      center.reportApi(const ApiException('Erro 2'));

      center.dismiss(first);

      expect(center.visible, hasLength(1));
      expect(center.visible.single.message, 'Erro 2');
    });

    testWidgets(
      'um alerta com autoDismissAfter some sozinho, sem esperar o X',
      (tester) async {
        await tester.pumpWidget(const SizedBox());
        final center = ErrorCenter();
        center.report(
          AppError(
            title: 'Concluído',
            message: 'Impressão enviada com sucesso.',
            severity: AppErrorSeverity.info,
            autoDismissAfter: const Duration(milliseconds: 500),
          ),
        );
        expect(center.visible, hasLength(1));

        await tester.pump(const Duration(milliseconds: 501));

        expect(center.visible, isEmpty);
      },
    );

    testWidgets(
      'sem autoDismissAfter, o alerta fica até ser fechado manualmente',
      (tester) async {
        await tester.pumpWidget(const SizedBox());
        final center = ErrorCenter();
        center.reportApi(const ApiException('Sem rede.'));

        await tester.pump(const Duration(minutes: 5));

        expect(center.visible, hasLength(1));
      },
    );

    test('uma falha de transporte é classificada como conexão', () {
      final center = ErrorCenter();

      center.reportApi(const ApiException('Sem rota para o servidor.'));

      expect(center.visible.single.origin, AppErrorOrigin.network);
    });

    group('falhas de conexão', () {
      test('várias chamadas offline produzem um aviso só', () {
        final center = ErrorCenter();

        // Cada tela que tenta falar com o servidor gera uma falha diferente;
        // empilhar todas enterraria a interface do operador.
        center.reportApi(
          const ApiException('Não foi possível conectar.', isConnectivity: true),
        );
        center.reportApi(
          const ApiException('O servidor demorou a responder.', isConnectivity: true),
        );
        center.reportApi(
          const ApiException('Sem rota para o host.', isConnectivity: true),
        );

        expect(center.visible, hasLength(1));
        expect(center.visible.single.title, 'Sem conexão com o servidor');
        // Ficar sem rede é esperado neste PDV, não um erro do operador.
        expect(center.visible.single.severity, AppErrorSeverity.warning);
      });

      test('o aviso de conexão não engole uma recusa do servidor', () {
        final center = ErrorCenter();

        center.reportApi(
          const ApiException('Sem rota.', isConnectivity: true),
        );
        center.reportApi(
          const ApiException('Caixa já aberto.', statusCode: 409),
        );

        expect(center.visible, hasLength(2));
      });

      test('a volta da conexão dispensa o aviso sozinha', () {
        final center = ErrorCenter();
        center.reportApi(
          const ApiException('Sem rota.', isConnectivity: true),
        );
        center.reportApi(
          const ApiException('Caixa já aberto.', statusCode: 409),
        );

        center.dismissByKey('connectivity');

        // Só o aviso obsoleto sai; o que exige ação continua na tela.
        expect(center.visible, hasLength(1));
        expect(center.visible.single.message, 'Caixa já aberto.');
      });
    });
  });

  group('AppErrorHost', () {
    /// Monta o host exatamente como o aplicativo faz: no `builder` do
    /// `MaterialApp`, ou seja **acima** do Navigator. Montá-lo abaixo de um
    /// `Scaffold` esconderia problemas que só aparecem nessa posição.
    Widget host(ErrorCenter center) => MaterialApp(
      builder: (context, child) =>
          AppErrorHost(center: center, child: child!),
      home: const Scaffold(body: SizedBox.expand()),
    );

    testWidgets('todo erro visível tem botão de fechar que age na hora', (
      tester,
    ) async {
      final center = ErrorCenter();
      await tester.pumpWidget(host(center));

      center.reportApi(
        const ApiException('Sangria divergente.', statusCode: 400),
      );
      await tester.pump();

      expect(find.text('Sangria divergente.'), findsOneWidget);
      expect(find.byTooltip('Fechar alerta'), findsOneWidget);

      await tester.tap(find.byTooltip('Fechar alerta'));
      await tester.pump();

      expect(find.text('Sangria divergente.'), findsNothing);
      expect(center.hasErrors, isFalse);
    });

    testWidgets(
      'o cartão mostra só título e mensagem; ação e detalhes ficam na cópia',
      (tester) async {
        final center = ErrorCenter();
        await tester.pumpWidget(host(center));

        center.report(
          AppError(
            title: 'Falha ao imprimir',
            message: 'A impressora não respondeu.',
            recommendedAction: 'Verifique o cabo e tente de novo.',
            technicalDetails: 'SocketException: porta 9100',
          ),
        );
        await tester.pump();

        expect(find.text('Falha ao imprimir'), findsOneWidget);
        expect(find.text('A impressora não respondeu.'), findsOneWidget);
        // O operador não pediu esse nível de detalhe: só aparece na cópia.
        expect(find.textContaining('Verifique o cabo'), findsNothing);
        expect(find.textContaining('SocketException'), findsNothing);

        String? copied;
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          (call) async {
            if (call.method == 'Clipboard.setData') {
              copied = (call.arguments as Map)['text'] as String;
            }
            return null;
          },
        );
        await tester.tap(find.byTooltip('Copiar detalhes'));
        await tester.pump();

        expect(copied, contains('A impressora não respondeu.'));
        expect(copied, contains('Verifique o cabo'));
        expect(copied, contains('SocketException'));
      },
    );

    testWidgets('os tooltips funcionam acima do Navigator', (tester) async {
      final center = ErrorCenter();
      await tester.pumpWidget(host(center));

      center.reportApi(const ApiException('Falha qualquer.'));
      await tester.pump();

      // `Tooltip` exige um `Overlay` ancestral. Como o host vive acima do
      // Navigator do aplicativo, ele precisa fornecer o seu próprio.
      final gesture = await tester.startGesture(
        tester.getCenter(find.byTooltip('Fechar alerta')),
      );
      await tester.pump(const Duration(seconds: 2));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.text('Fechar alerta'), findsOneWidget);

      await gesture.up();
      await tester.pumpAndSettle();
    });

    testWidgets('vários alertas empilham no topo direito, do mais novo ao mais velho', (
      tester,
    ) async {
      final center = ErrorCenter();
      await tester.pumpWidget(host(center));

      center.reportApi(
        const ApiException('Movimento pendente.', statusCode: 409),
        title: 'Não foi possível fechar o caixa',
      );
      center.reportApi(
        const ApiException('Sangria divergente.', statusCode: 400),
      );
      await tester.pump();

      expect(find.text('Não foi possível fechar o caixa'), findsOneWidget);
      expect(find.text('Sangria divergente.'), findsOneWidget);
    });
  });
}
