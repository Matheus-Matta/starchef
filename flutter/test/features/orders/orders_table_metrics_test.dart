import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';
import 'package:starchef_pdv/features/orders/presentation/orders_table_metrics.dart';

void main() {
  group('quantas linhas de pedido cabem', () {
    test('numa tela apertada sobra pelo menos uma linha', () {
      expect(OrdersTableMetrics.rowsThatFit(0), 1);
      expect(OrdersTableMetrics.rowsThatFit(-500), 1);
    });

    test('o espaço decide, e não um teto de dez', () {
      // Uma tela de balcão: antes parava em 10 linhas e deixava um vão sem
      // nada abaixo da paginação.
      expect(OrdersTableMetrics.rowsThatFit(900), greaterThan(10));
    });

    testWidgets('a conta cabe de verdade, sem estourar nem sobrar faixa', (
      tester,
    ) async {
      // A tabela paginada não rola por dentro: ela desenha o número de linhas
      // que mandarem. Se a reserva de `chrome` estiver curta, o teste falha
      // com overflow; se estiver folgada demais, sobra espaço em branco — e é
      // isso que a segunda expectativa mede.
      addTearDown(tester.view.reset);

      for (final altura in <double>[300, 520, 768, 1040]) {
        // A janela do teste tem 600 px de altura por padrão: sem isto, um
        // `SizedBox` de 768 é espremido para 600 e o que falha é o teste, não
        // a conta.
        tester.view.physicalSize = Size(1000, altura);
        tester.view.devicePixelRatio = 1;

        final linhas = OrdersTableMetrics.rowsThatFit(altura);

        await tester.pumpWidget(
          MaterialApp(
            theme: AppTheme.light(),
            home: Scaffold(
              body: SizedBox.expand(
                child: Builder(
                  builder: (context) => PaginatedDataTable(
                    showCheckboxColumn: false,
                    dataRowMinHeight: AppTheme.tableRowHeight,
                    dataRowMaxHeight: AppTheme.tableRowHeight,
                    rowsPerPage: linhas,
                    availableRowsPerPage: <int>[linhas],
                    onRowsPerPageChanged: (_) {},
                    columns: const [
                      DataColumn(label: Text('Pedido')),
                      DataColumn(label: Text('Total')),
                    ],
                    source: _FonteFalsa(linhas * 3),
                  ),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(
          tester.takeException(),
          isNull,
          reason: 'a tabela estourou em ${altura}px com $linhas linhas',
        );

        final alturaUsada = tester
            .getSize(find.byType(PaginatedDataTable))
            .height;
        expect(
          altura - alturaUsada,
          lessThan(AppTheme.tableRowHeight),
          reason:
              'sobrou espaço para mais uma linha em ${altura}px '
              '(usou $alturaUsada)',
        );
      }
    });
  });
}

class _FonteFalsa extends DataTableSource {
  _FonteFalsa(this.total);

  final int total;

  @override
  DataRow? getRow(int index) => index >= total
      ? null
      : DataRow.byIndex(
          index: index,
          cells: [
            DataCell(Text('#$index')),
            DataCell(
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.edit_outlined),
              ),
            ),
          ],
        );

  @override
  int get rowCount => total;

  @override
  bool get isRowCountApproximate => false;

  @override
  int get selectedRowCount => 0;
}
