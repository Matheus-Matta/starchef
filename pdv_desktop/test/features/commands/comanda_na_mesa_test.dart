import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/command_detail_view.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/table_details_panel.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/command_attach_dialog.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/command_attach_dialog_body.dart';

/// Onde o cartão está sentado — e quem está sentado na mesa.
///
/// Antes, vincular comanda e mesa só existia no meio do fluxo de abrir pedido:
/// um cartão que sentou na mesa errada só era corrigido na hora de cobrar, e a
/// tela da mesa era só leitura. Estes testes cobrem os dois lados do mesmo
/// vínculo, cada um na tela em que o operador está quando percebe o erro.
void main() {
  Widget moldura(Widget filho) => MaterialApp(
    home: ShadTheme(
      data: AppTheme.shadLight(),
      child: Scaffold(body: filho),
    ),
  );

  Widget detalhe({
    Map<String, dynamic>? comanda,
    VoidCallback? onEscolherMesa,
  }) => moldura(
    CommandDetailView(
      comanda: comanda ?? {'id': 'c1', 'number': '12'},
      itens: const [],
      produtos: const [],
      todosOsProdutos: const [],
      categorias: const [],
      categoria: null,
      termoDeProduto: '',
      carregando: false,
      enviando: false,
      imprimindo: false,
      onVoltar: () {},
      onBuscaDeProduto: (_) {},
      onCategoria: (_) {},
      onProduto: (_) {},
      onSendToKitchen: () {},
      onPrintReceipt: () {},
      onVoidItem: (_) {},
      onEscolherMesa: onEscolherMesa,
    ),
  );

  group('o cartao aberto diz em que mesa esta', () {
    testWidgets('sem mesa, o botao CONVIDA em vez de afirmar', (tester) async {
      await tester.pumpWidget(detalhe(onEscolherMesa: () {}));

      expect(find.text('Sem mesa'), findsOneWidget);
    });

    testWidgets('com mesa, o botao mostra QUAL', (tester) async {
      await tester.pumpWidget(
        detalhe(
          comanda: {'id': 'c1', 'number': '12', 'current_table_number': '7'},
          onEscolherMesa: () {},
        ),
      );

      expect(find.widgetWithText(OutlinedButton, 'Mesa 7'), findsOneWidget);
    });

    testWidgets('salao sem mesa nenhuma nao mostra o botao', (tester) async {
      // Um botão que só abre um diálogo vazio ensina o operador a ignorar
      // botões — a página passa `null` quando não há mesas cadastradas.
      await tester.pumpWidget(detalhe());

      expect(find.text('Sem mesa'), findsNothing);
      expect(find.byIcon(Icons.table_restaurant_outlined), findsNothing);
    });
  });

  group('a tela da mesa mexe nas comandas sentadas nela', () {
    final mesa = {
      'id': 't1',
      'number': '7',
      'capacity': 4,
      'active_commands': [
        {'id': 'c1', 'number': '12', 'code': 'ABC'},
      ],
    };

    testWidgets('o X de cada linha tira AQUELA comanda', (tester) async {
      Map<String, dynamic>? saiu;
      await tester.pumpWidget(
        moldura(
          TableDetailsPanel(
            table: mesa,
            onBack: () {},
            onOpenCommand: (_) {},
            onUnlinkCommand: (cmd) => saiu = cmd,
          ),
        ),
      );

      await tester.tap(find.byTooltip('Tirar a comanda 12 desta mesa'));
      await tester.pump();

      expect(saiu?['id'], 'c1');
    });

    testWidgets('sem quem desvincule, o X nao aparece ativo', (tester) async {
      // A tela ocupada passa `null`: um X que não faz nada é pior do que um X
      // apagado, porque o operador toca de novo achando que falhou.
      await tester.pumpWidget(
        moldura(
          TableDetailsPanel(table: mesa, onBack: () {}, onOpenCommand: (_) {}),
        ),
      );

      final botao = tester.widget<IconButton>(
        find.ancestor(
          of: find.byIcon(Icons.close),
          matching: find.byType(IconButton),
        ),
      );
      expect(botao.onPressed, isNull);
    });

    testWidgets('e ha por onde sentar MAIS uma', (tester) async {
      var chamou = false;
      await tester.pumpWidget(
        moldura(
          TableDetailsPanel(
            table: mesa,
            onBack: () {},
            onOpenCommand: (_) {},
            onAddCommand: () => chamou = true,
          ),
        ),
      );

      await tester.tap(find.text('Vincular comanda'));
      await tester.pump();

      expect(chamou, isTrue);
    });
  });

  group('o mesmo dialogo serve a venda e a mesa', () {
    final livre = {
      'id': 'c9',
      'number': '9',
      'code': 'C009',
      'pending_total': '0',
    };
    final ocupada = {
      'id': 'c1',
      'number': '1',
      'code': 'C001',
      'pending_total': '30.00',
    };

    Widget dialogo({required bool somenteComConta}) => moldura(
      CommandAttachDialog(
        commands: [livre, ocupada],
        attached: const [],
        totals: const {},
        title: 'Comandas',
        somenteComConta: somenteComConta,
      ),
    );

    testWidgets('na VENDA, cartao sem conta nao entra na lista', (
      tester,
    ) async {
      await tester.pumpWidget(dialogo(somenteComConta: true));

      expect(find.text('C001'), findsOneWidget);
      expect(find.text('C009'), findsNothing);
    });

    testWidgets('na MESA, cartao livre e o caso normal', (tester) async {
      // Sentar um cartão zerado na mesa é o começo do atendimento; filtrar
      // por consumo aqui esvaziaria a lista justamente no gesto mais comum.
      await tester.pumpWidget(dialogo(somenteComConta: false));

      expect(find.text('C009'), findsOneWidget);
      expect(find.text('C001'), findsOneWidget);
    });

    testWidgets('o X do cartao ja sentado devolve um DETACH', (tester) async {
      CommandAttachResult? resultado;
      await tester.pumpWidget(
        moldura(
          Builder(
            builder: (context) => TextButton(
              onPressed: () async {
                resultado = await showCommandAttachDialog(
                  context,
                  commands: [livre],
                  attached: [ocupada],
                  somenteComConta: false,
                );
              },
              child: const Text('abrir'),
            ),
          ),
        ),
      );

      await tester.tap(find.text('abrir'));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Retirar comanda 1'));
      await tester.pumpAndSettle();

      expect(resultado?.isDetach, isTrue);
      expect(resultado?.detachedId, 'c1');
    });
  });
}
