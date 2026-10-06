import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/resource_page.dart';
import 'package:starchef_pdv_mobile/core/widgets/paginated_picker.dart';
import 'package:starchef_pdv_mobile/features/menu/presentation/category_chips_bar.dart';

/// O garçom acha o produto tocando na categoria, sem digitar.
///
/// Antes só havia a busca por texto: com o cardápio inteiro numa lista só, o
/// garçom rolava dezenas de itens com o cliente esperando.
void main() {
  Widget app(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('a barra mostra "Todas" primeiro e avisa a categoria tocada', (
    tester,
  ) async {
    String? escolhida = 'nada';
    await tester.pumpWidget(
      app(
        CategoryChipsBar(
          categories: const [
            {'id': 'beb', 'name': 'Bebidas'},
            {'id': 'lan', 'name': 'Lanches'},
          ],
          selectedId: null,
          onSelected: (id) => escolhida = id,
        ),
      ),
    );

    final rotulos = tester
        .widgetList<ChoiceChip>(find.byType(ChoiceChip))
        .map((chip) => (chip.label as Text).data)
        .toList();
    expect(rotulos, ['Todas', 'Bebidas', 'Lanches']);

    await tester.tap(find.text('Lanches'));
    expect(escolhida, 'lan');
    await tester.tap(find.text('Todas'));
    expect(escolhida, isNull);
  });

  testWidgets('trocar a categoria recarrega a lista do começo', (tester) async {
    final chamadas = <String>[];
    Widget lista(String? categoria) => app(
      PaginatedPicker(
        searchHint: 'Buscar produto',
        filterKey: categoria,
        fetch: (page, search) async {
          chamadas.add('$categoria:$page');
          return ResourcePage(
            rows: [
              {'name': 'Item de $categoria'},
            ],
            hasMore: false,
          );
        },
        itemBuilder: (context, row) => Text('${row['name']}'),
      ),
    );

    await tester.pumpWidget(lista(null));
    await tester.pumpAndSettle();
    await tester.pumpWidget(lista('beb'));
    await tester.pumpAndSettle();

    expect(chamadas, ['null:1', 'beb:1']);
    expect(find.text('Item de beb'), findsOneWidget);
    expect(find.text('Item de null'), findsNothing);
  });
}
