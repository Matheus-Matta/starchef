import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error_host.dart';
import 'package:starchef_pdv_desktop/core/errors/error_center.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';

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
        // `failure`, e não `info`: desde que só falha interrompe a tela, um
        // `info` nem chega em `visible` — ele vai direto para o sino. O que
        // este teste mede é o auto-dismiss, então precisa de algo que apareça.
        center.report(
          AppError(
            title: 'Não deu certo',
            message: 'A impressora não respondeu.',
            severity: AppErrorSeverity.failure,
            autoDismissAfter: const Duration(milliseconds: 500),
          ),
        );
        expect(center.visible, hasLength(1));

        await tester.pump(const Duration(milliseconds: 501));

        expect(center.visible, isEmpty);
      },
    );

    testWidgets(
      'sem autoDismissAfter, o alerta some sozinho depois do tempo padrão',
      (tester) async {
        await tester.pumpWidget(const SizedBox());
        final center = ErrorCenter();
        center.reportApi(const ApiException('Sem rede.'));
        expect(center.visible, hasLength(1));

        // Falha, aviso e confirmação somem sozinhos igualmente — o `X`
        // só adianta o fechamento, não é a única saída.
        await tester.pump(ErrorCenter.defaultAutoDismissAfter);
        await tester.pump(const Duration(milliseconds: 1));

        expect(center.visible, isEmpty);
      },
    );

    test('uma falha de transporte é classificada como conexão', () {
      final center = ErrorCenter();

      center.reportApi(
        const ApiException('Sem rota para o servidor.', isConnectivity: true),
      );

      expect(center.visible.single.origin, AppErrorOrigin.network);
    });

    test('recusa local não é apresentada como falha de rede', () {
      // Sem status HTTP e sem `isConnectivity`, a recusa nasceu aqui dentro —
      // uma regra da tela ou do banco local. Um caso real: "somente dinheiro
      // pode ter valor recebido maior que o restante" aparecia como "Servidor
      // indisponível / Origem: Conexão / Verifique a rede e tente novamente",
      // mandando o operador atrás de um problema de rede inexistente enquanto
      // a correção estava na própria tela.
      final center = ErrorCenter();

      center.reportApi(
        const ApiException(
          'Somente dinheiro pode ter valor recebido maior que o restante.',
        ),
      );

      final error = center.visible.single;
      expect(error.origin, AppErrorOrigin.application);
      expect(error.title, isNot('Servidor indisponível'));
      expect(error.recommendedAction, isNot(contains('rede')));
      expect(
        error.message,
        'Somente dinheiro pode ter valor recebido maior que o restante.',
      );
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
        // Este PDV só opera conectado: sem rede a operação NÃO ACONTECEU, e
        // não ficou guardada em lugar nenhum. Um aviso amarelo faria o
        // operador seguir para a próxima venda achando que esta entrou.
        expect(center.visible.single.severity, AppErrorSeverity.failure);
        expect(
          center.visible.single.recommendedAction,
          contains('Nada foi registrado'),
        );
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
        // Cancela o timer de auto-dismiss ainda pendente: o binding de teste
        // de widget não aceita terminar com um `Timer` agendado no ar.
        center.dismissAll();
      },
    );

    testWidgets('os tooltips funcionam acima do Navigator', (tester) async {
      final center = ErrorCenter();
      await tester.pumpWidget(host(center));

      // Tempo de sobra explícito: o teste segura o gesto por 2s para o
      // tooltip aparecer, o que não pode competir com o próprio alerta
      // sumindo sozinho no meio do gesto.
      center.report(
        AppError(
          title: 'Falha qualquer',
          message: 'Falha qualquer.',
          autoDismissAfter: const Duration(minutes: 5),
        ),
      );
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
      center.dismissAll();
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
      center.dismissAll();
    });
  });

  group('o sino e a regra de quem interrompe a tela', () {
    test('só falha aparece na tela; o resto vai para o sino', () {
      final centro = ErrorCenter();
      addTearDown(centro.dispose);

      centro.report(AppError(
        title: 'Concluído', message: 'Venda registrada.',
        severity: AppErrorSeverity.success,
      ));
      centro.report(AppError(
        title: 'Atenção', message: 'NFC-e ainda não autorizada.',
        severity: AppErrorSeverity.warning,
      ));
      centro.report(AppError(
        title: 'Não deu certo', message: 'Impressora não respondeu.',
        severity: AppErrorSeverity.failure,
      ));

      expect(centro.visible.length, 1,
          reason: 'sucesso e aviso não podem cobrir a tela do operador');
      expect(centro.visible.single.severity, AppErrorSeverity.failure);
      expect(centro.history.length, 3,
          reason: 'o sino guarda tudo — inclusive o que não interrompeu');
    });

    test('a notificação 21 empurra a mais antiga', () {
      final centro = ErrorCenter();
      addTearDown(centro.dispose);

      for (var i = 1; i <= 21; i++) {
        centro.report(AppError(
          title: 'Aviso $i', message: 'mensagem $i',
          severity: AppErrorSeverity.info,
        ));
      }

      expect(centro.history.length, 20);
      expect(centro.history.first.title, 'Aviso 21', reason: 'a mais nova no topo');
      expect(centro.history.last.title, 'Aviso 2',
          reason: 'a de número 1 saiu quando a 21 entrou');
    });

    test('o contador de novas zera ao abrir o sino', () {
      final centro = ErrorCenter();
      addTearDown(centro.dispose);

      centro.report(AppError(
        title: 'a', message: 'a', severity: AppErrorSeverity.success));
      centro.report(AppError(
        title: 'b', message: 'b', severity: AppErrorSeverity.info));
      expect(centro.unreadCount, 2);

      centro.markAllSeen();
      expect(centro.unreadCount, 0);
      expect(centro.history.length, 2, reason: 'ver não é apagar');
    });

    test('o contador nunca fica negativo quando o teto descarta', () {
      final centro = ErrorCenter(maximumHistory: 3);
      addTearDown(centro.dispose);

      for (var i = 0; i < 3; i++) {
        centro.report(AppError(
          title: 'n$i', message: 'm$i', severity: AppErrorSeverity.info));
      }
      centro.markAllSeen();
      for (var i = 3; i < 6; i++) {
        centro.report(AppError(
          title: 'n$i', message: 'm$i', severity: AppErrorSeverity.info));
      }

      expect(centro.unreadCount, greaterThanOrEqualTo(0));
      expect(centro.unreadCount, lessThanOrEqualTo(centro.history.length));
    });

    test('o dedupe também vale no sino', () {
      final centro = ErrorCenter();
      addTearDown(centro.dispose);

      for (var i = 0; i < 10; i++) {
        centro.report(AppError(
          title: 'Sem conexão', message: 'Não foi possível falar com a retaguarda.',
          severity: AppErrorSeverity.failure, dedupeKey: 'rede',
        ));
      }

      expect(centro.history.length, 1,
          reason: 'dez tentativas sem rede são um assunto só, não dez linhas');
    });

    test('limpar o sino não mexe no que está na tela', () {
      final centro = ErrorCenter();
      addTearDown(centro.dispose);

      centro.report(AppError(
        title: 'x', message: 'y', severity: AppErrorSeverity.failure));
      expect(centro.visible.length, 1);

      centro.clearHistory();

      expect(centro.history, isEmpty);
      expect(centro.visible.length, 1, reason: 'o erro na tela ainda exige reação');
    });
  });
}
