import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/commands_grid.dart';

/// O salão de comandas: a grade e a barra de busca acima dela.
Widget _tela(List<Map<String, dynamic>> comandas) => MaterialApp(
  home: Scaffold(
    body: CommandsGrid(
      comandas: comandas,
      carregando: false,
      controladorDaBusca: TextEditingController(),
      controladorDoLeitor: TextEditingController(),
      focoDoLeitor: FocusNode(),
      onBuscaMudou: () {},
      onLeitura: () {},
      onAbrir: (_) {},
    ),
  ),
);

Future<void> _montar(WidgetTester tester, Widget tela) async {
  // A resolução REAL de um posto de venda. O canvas padrão do teste é 800×600,
  // que não existe em balcão nenhum.
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(tela);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('os dois campos da barra ficam alinhados', (tester) async {
    // Eles tinham decorações diferentes — um com rótulo e ajuda, outro só com
    // `hint` — e um `TextField` com rótulo é mais alto. Lado a lado numa `Row`
    // isso desalinha as caixas, e o desencontro salta aos olhos porque os dois
    // ficam colados.
    await _montar(tester, _tela(const []));

    final campos = find.byType(TextField);
    expect(campos, findsNWidgets(2));

    final leitor = tester.getRect(campos.at(0));
    final busca = tester.getRect(campos.at(1));

    expect(leitor.top, busca.top, reason: 'topo desalinhado');
    expect(leitor.height, busca.height, reason: 'alturas diferentes');
  });

  testWidgets('a grade mostra um cartao por comanda', (tester) async {
    await _montar(
      tester,
      _tela(const [
        {'id': 'c1', 'number': 1, 'code': 'CMD-0001', 'pending_items': 0},
        {'id': 'c2', 'number': 2, 'code': 'CMD-0002', 'pending_items': 3},
      ]),
    );

    expect(find.text('1'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
    // O estado sai da contagem de pendentes, não de um campo gravado.
    expect(find.textContaining('LIVRE'), findsOneWidget);
    expect(find.textContaining('OCUPADA'), findsOneWidget);
  });
}
