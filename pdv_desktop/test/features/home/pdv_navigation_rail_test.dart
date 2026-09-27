import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_navigation_rail.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_navigation_shell.dart';

/// O trilho é o ÚNICO caminho até as telas do PDV.
///
/// O defeito: `PdvDestination.customers` existia no enum, `_navigateTo` o
/// tratava e a tela era desenhada — mas nenhum botão o selecionava, e o
/// cadastro de cliente ficou inalcançável no desktop inteiro. Uma segunda
/// lista de destinos (`PdvSidebar`), que ninguém usa, tinha a entrada e fazia
/// parecer que estava tudo no lugar.
void main() {
  Future<void> montar(
    WidgetTester tester, {
    bool showOrders = true,
    bool showFinance = true,
    ValueChanged<PdvDestination>? onSelected,
  }) => tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: PdvNavigationRail(
          selected: PdvDestination.sale,
          onSelected: onSelected ?? (_) {},
          showOrders: showOrders,
          showFinance: showFinance,
        ),
      ),
    ),
  );

  testWidgets('o trilho oferece TODOS os destinos do enum', (tester) async {
    // Fixa a classe inteira do defeito, e não só o Clientes: um destino novo
    // sem entrada aqui nasce inalcançável e o teste avisa.
    await montar(tester);

    for (final destino in PdvDestination.values) {
      expect(
        find.byWidgetPredicate(
          (widget) => widget is Tooltip && widget.message == _rotulo(destino),
        ),
        findsOneWidget,
        reason: 'destino $destino não tem botão no trilho',
      );
    }
  });

  testWidgets('Clientes leva ao destino de clientes', (tester) async {
    PdvDestination? escolhido;
    await montar(tester, onSelected: (destino) => escolhido = destino);

    await tester.tap(find.text('Clientes'));
    await tester.pump();

    expect(escolhido, PdvDestination.customers);
  });

  testWidgets('pedidos e caixa somem sem permissão, clientes fica', (
    tester,
  ) async {
    await montar(tester, showOrders: false, showFinance: false);

    expect(find.text('Pedidos'), findsNothing);
    expect(find.text('Caixa'), findsNothing);
    expect(find.text('Clientes'), findsOneWidget);
  });
}

/// O rótulo que o trilho usa para cada destino — "Mais" e "Caixa" não repetem
/// o nome do enum, e é por eles que o operador encontra a tela.
String _rotulo(PdvDestination destino) => switch (destino) {
  PdvDestination.sale => 'Venda',
  PdvDestination.orders => 'Pedidos',
  PdvDestination.tables => 'Mesas',
  PdvDestination.commands => 'Comandas',
  PdvDestination.customers => 'Clientes',
  PdvDestination.finance => 'Caixa',
  PdvDestination.scale => 'Balança',
  PdvDestination.settings => 'Mais',
};
