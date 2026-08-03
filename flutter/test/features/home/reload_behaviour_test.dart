import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Reproduz as três formas de sinalizar carregamento que o PDV usa, para
/// fixar a diferença entre elas.
///
/// O operador relatou que "tudo dá reload": qualquer oscilação de rede, voltar
/// ao início ou abrir uma mesa devolvia o PDV a uma tela em branco no meio do
/// atendimento. A regra que ficou: só a primeira carga pode apagar a tela.
void main() {
  Widget screen({
    required bool firstLoad,
    required bool refreshing,
    required bool busy,
  }) => MaterialApp(
    home: Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(
            tooltip: refreshing ? 'Atualizando...' : 'Atualizar',
            onPressed: refreshing ? null : () {},
            icon: refreshing
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh),
          ),
        ],
      ),
      body: firstLoad
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                const Center(child: Text('Pedido #42')),
                if (busy)
                  const Positioned(
                    top: 0,
                    left: 0,
                    right: 0,
                    child: LinearProgressIndicator(minHeight: 3),
                  ),
              ],
            ),
    ),
  );

  testWidgets('a primeira carga pode ocupar a tela — não há o que mostrar', (
    tester,
  ) async {
    await tester.pumpWidget(
      screen(firstLoad: true, refreshing: false, busy: false),
    );

    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.text('Pedido #42'), findsNothing);
  });

  testWidgets('uma recarga de fundo preserva o pedido na tela', (tester) async {
    await tester.pumpWidget(
      screen(firstLoad: false, refreshing: true, busy: false),
    );

    // Este é o caso da rede caindo e voltando: o operador continua no mesmo
    // pedido, e o único sinal fica no botão de atualizar.
    expect(find.text('Pedido #42'), findsOneWidget);
    expect(find.byTooltip('Atualizando...'), findsOneWidget);
  });

  testWidgets('uma operação em curso não cobre a tela', (tester) async {
    await tester.pumpWidget(
      screen(firstLoad: false, refreshing: false, busy: true),
    );

    // Abrir mesa, incluir item e pagar passavam por um overlay escuro com
    // spinner central; agora é só uma faixa no topo.
    expect(find.text('Pedido #42'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('sem nada em andamento, nenhum indicador aparece', (
    tester,
  ) async {
    await tester.pumpWidget(
      screen(firstLoad: false, refreshing: false, busy: false),
    );

    expect(find.text('Pedido #42'), findsOneWidget);
    expect(find.byType(LinearProgressIndicator), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.byTooltip('Atualizar'), findsOneWidget);
  });
}
