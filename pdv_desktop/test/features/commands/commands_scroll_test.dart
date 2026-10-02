import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_pager.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/command_picker.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/commands_paged_grid.dart';

/// Uma loja com [total] comandas no servidor, 50 por página.
class _Loja extends CommandRepository {
  _Loja(this.total) : super(ApiClient(baseUrl: 'http://x'));

  final int total;
  final pedidos = <String>[];

  @override
  Future<PaginaDeComandas> page({
    required int pagina,
    String busca = '',
    String? restaurantId,
  }) async {
    pedidos.add('$pagina:$busca');
    final todas = [
      for (var n = 1; n <= total; n++)
        if (busca.isEmpty || '$n'.contains(busca))
          {'id': 'c$n', 'number': n, 'code': 'CMD-$n', 'status': 'free'},
    ];
    final inicio = (pagina - 1) * 50;
    final fim = (inicio + 50).clamp(0, todas.length);
    return (
      itens: inicio >= todas.length
          ? <Map<String, dynamic>>[]
          : todas.sublist(inicio, fim),
      temMais: fim < todas.length,
      total: todas.length,
    );
  }
}

Future<void> _montar(WidgetTester tester, Widget corpo, {Size? tela}) async {
  tester.view.physicalSize = tela ?? const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      builder: (context, child) =>
          ShadTheme(data: AppTheme.shadLight(), child: child!),
      home: Scaffold(body: corpo),
    ),
  );
  await tester.pumpAndSettle();
}

Widget _grade(CommandPager paginador) => CommandsPagedGrid(
  paginador: paginador,
  vazio: (_) => const Text('vazio'),
  itemBuilder: (_, c) => Card(child: Center(child: Text('#${c['number']}'))),
);

void main() {
  testWidgets('rolar até o fim traz a próxima página, até acabar', (
    tester,
  ) async {
    final loja = _Loja(200);
    final paginador = CommandPager(
      ({required int pagina, String busca = ''}) =>
          loja.page(pagina: pagina, busca: busca),
    );
    addTearDown(paginador.dispose);
    paginador.recomecar();
    await _montar(tester, _grade(paginador));

    // Abre sem esperar as 200: uma página (ou duas, se o fim da primeira já
    // está perto o bastante para adiantar a seguinte).
    expect(loja.pedidos.length, lessThan(3));
    expect(paginador.itens.length, lessThan(200));
    expect(find.text('#200'), findsNothing);

    // Rola até o fim várias vezes: cada chegada pede mais uma página.
    for (var i = 0; i < 6; i++) {
      await tester.drag(find.byType(CustomScrollView), const Offset(0, -5000));
      await tester.pumpAndSettle();
    }

    expect(loja.pedidos, ['1:', '2:', '3:', '4:']);
    expect(paginador.itens, hasLength(200));
    expect(find.text('#200'), findsOneWidget);
    expect(find.text('200 comandas'), findsOneWidget);
  });

  testWidgets(
    'tela alta que não enche com uma página pede a seguinte sozinha',
    (tester) async {
      // Sem barra de rolagem não haveria rolagem para pedir a página 2: a
      // comanda 60 nunca apareceria num monitor grande.
      final loja = _Loja(60);
      final paginador = CommandPager(
        ({required int pagina, String busca = ''}) =>
            loja.page(pagina: pagina, busca: busca),
      );
      addTearDown(paginador.dispose);
      paginador.recomecar();
      await _montar(tester, _grade(paginador), tela: const Size(2400, 4000));

      expect(loja.pedidos, ['1:', '2:']);
      expect(find.text('#60'), findsOneWidget);
    },
  );

  group('selecionar a comanda na venda', () {
    late List<Map<String, dynamic>> abertas;

    Future<_Loja> abrirSeletor(
      WidgetTester tester, {
      List<Map<String, dynamic>> catalogo = const [],
    }) async {
      abertas = [];
      final loja = _Loja(500);
      await _montar(
        tester,
        CommandPicker(
          repository: loja,
          catalogo: catalogo,
          onOpen: abertas.add,
        ),
      );
      return loja;
    }

    testWidgets('digitar o número busca no servidor a comanda que não desceu', (
      tester,
    ) async {
      final loja = await abrirSeletor(tester);
      expect(find.text('480'), findsNothing);

      await tester.enterText(find.byType(TextField), '480');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(loja.pedidos.last, '1:480');
      expect(find.widgetWithText(InkWell, '480'), findsOneWidget);
    });

    testWidgets('Enter abre a de número EXATO, não a primeira que contém', (
      tester,
    ) async {
      await abrirSeletor(tester);

      // "12" casa com 12, 112, 120…; o Enter do leitor sai antes da espera
      // da digitação e ainda assim abre a 12.
      await tester.enterText(find.byType(TextField), '12');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();

      expect(abertas.single['number'], 12);
    });

    testWidgets('Enter sem número exato e com várias não abre ninguém', (
      tester,
    ) async {
      await abrirSeletor(tester);

      await tester.enterText(find.byType(TextField), '9999');
      await tester.testTextInput.receiveAction(TextInputAction.done);
      await tester.pumpAndSettle();

      expect(abertas, isEmpty);
      expect(find.text('Nenhuma comanda encontrada'), findsOneWidget);
    });

    testWidgets('mostra o estado do catálogo, que o tempo real mantém em dia', (
      tester,
    ) async {
      // A página veio com a 3 livre; o catálogo já sabe que outro caixa a
      // ocupou. Abrir a versão velha retomaria a comanda sem o pedido.
      await abrirSeletor(
        tester,
        catalogo: [
          {
            'id': 'c3',
            'number': 3,
            'status': 'occupied',
            'current_order_id': 'o9',
          },
        ],
      );

      final cartao = find.ancestor(
        of: find.text('3'),
        matching: find.byType(InkWell),
      );
      expect(
        find.descendant(of: cartao, matching: find.text('Em uso')),
        findsOneWidget,
      );
      await tester.tap(find.text('3'));
      expect(abertas.single['current_order_id'], 'o9');
    });
  });
}
