import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/commands_page.dart';

class _Repositorio extends CommandRepository {
  _Repositorio() : super(ApiClient(baseUrl: 'http://x'));

  var lancamentos = 0;
  num? quantidade;
  List<String> adicionais = const [];

  @override
  Future<List<Map<String, dynamic>>> list({String? restaurantId}) async => [
    {
      'id': 'comanda-13',
      'number': 13,
      'code': 'CMD-0013',
      'pending_items': 0,
      'pending_total': '0.00',
    },
  ];

  @override
  Future<Map<String, dynamic>> items(
    String commandId, {
    bool history = false,
  }) async => const {'items': []};

  @override
  Future<Map<String, dynamic>> launchItem(
    String commandId, {
    required String productId,
    num quantity = 1,
    String customerNote = '',
    List<String> variationIds = const [],
    List<String> addonIds = const [],
  }) async {
    lancamentos++;
    quantidade = quantity;
    adicionais = addonIds;
    return const {};
  }
}

void main() {
  testWidgets('produto com adicional abre a configuracao antes de lancar', (
    tester,
  ) async {
    final repositorio = _Repositorio();
    await _montar(tester, repositorio, const [
      {
        'id': 'produto-1',
        'name': 'Hamburguer',
        'current_price': '20.00',
        'addons': [
          {'id': 'adicional-1', 'name': 'Bacon', 'price': '3.00'},
        ],
      },
    ]);

    await _abrirComandaETocarProduto(tester, 'Hamburguer');

    expect(find.text('Adicionais'), findsOneWidget);
    expect(find.textContaining('Bacon'), findsOneWidget);
    expect(repositorio.lancamentos, 0);

    await tester.tap(find.textContaining('Bacon'));
    await tester.tap(find.text('Adicionar (Enter)'));
    await tester.pumpAndSettle();

    expect(repositorio.lancamentos, 1);
    expect(repositorio.adicionais, ['adicional-1']);
  });

  testWidgets('produto por quilo abre o campo de peso antes de lancar', (
    tester,
  ) async {
    final repositorio = _Repositorio();
    await _montar(tester, repositorio, const [
      {
        'id': 'produto-kg',
        'name': 'Picanha por kg',
        'current_price': '89.90',
        'pricing_unit': 'kg',
      },
    ]);

    await _abrirComandaETocarProduto(tester, 'Picanha por kg');

    expect(find.byKey(const Key('product-weight')), findsOneWidget);
    expect(find.text('Peso'), findsOneWidget);
    expect(repositorio.lancamentos, 0);

    await tester.enterText(find.byKey(const Key('product-weight')), '0,750');
    await tester.pump();
    await tester.tap(find.text('Adicionar (Enter)'));
    await tester.pumpAndSettle();

    expect(repositorio.lancamentos, 1);
    expect(repositorio.quantidade, .75);
  });
}

Future<void> _montar(
  WidgetTester tester,
  CommandRepository repositorio,
  List<Map<String, dynamic>> produtos,
) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(
    MaterialApp(
      home: ShadTheme(
        data: AppTheme.shadLight(),
        child: Scaffold(
          body: CommandsPage(
            repository: repositorio,
            products: produtos,
            categories: const [],
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _abrirComandaETocarProduto(
  WidgetTester tester,
  String produto,
) async {
  await tester.tap(find.text('13'));
  await tester.pumpAndSettle();
  await tester.tap(find.text(produto));
  await tester.pumpAndSettle();
}
