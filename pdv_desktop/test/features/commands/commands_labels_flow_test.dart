import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/commands_labels.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/commands_loading.dart';

/// O lote de etiquetas do começo ao fim: faixa, impressora, uma a uma.
class _Repo extends CommandRepository {
  _Repo()
    : super(
        ApiClient(baseUrl: 'http://starchef.test/api/v1'),
        accessToken: 't',
      );

  // A comanda 12 não está cadastrada.
  final cadastradas = [10, 11, 13];

  @override
  Future<List<Map<String, dynamic>>> inRange({
    required int de,
    required int ate,
    String? restaurantId,
  }) async => [
    for (final n in cadastradas)
      if (n >= de && n <= ate) {'id': 'c$n', 'number': n, 'code': '00$n'},
  ];

  @override
  Future<List<Map<String, dynamic>>> printers({String? restaurantId}) async => [
    {
      'id': 'p1',
      'name': 'Etiquetas',
      'connection_type': 'network',
      'host': '10.0.0.9',
      'port': 9100,
    },
  ];
}

class _Tela extends StatefulWidget {
  const _Tela(this.imprimir);
  final Future<void> Function(Map<String, dynamic>, Map<String, dynamic>)
  imprimir;
  @override
  State<_Tela> createState() => _TelaState();
}

class _TelaState extends State<_Tela>
    with CommandsLoading<_Tela>, CommandsLabels<_Tela> {
  @override
  final repository = _Repo();
  @override
  String? get restaurantId => 'r1';
  @override
  String? get restaurantIdDaTela => 'r1';
  @override
  final leitor = TextEditingController();
  @override
  final focoDoLeitor = FocusNode();
  @override
  Stream<String>? get codigosLidos => null;
  @override
  Future<void> Function(Map<String, dynamic>, Map<String, dynamic>)
  get imprimirNoTerminal => widget.imprimir;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      ElevatedButton(
        onPressed: imprimirEtiquetas,
        child: const Text('etiquetas'),
      ),
      Text('erro:$erro'),
      Text('recado:$recado'),
    ],
  );
}

void main() {
  late List<String> impressas;

  Future<void> pedirLote(
    WidgetTester tester,
    Future<void> Function(Map<String, dynamic>, Map<String, dynamic>) imprimir,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadLight(), child: child!),
        home: Scaffold(body: _Tela(imprimir)),
      ),
    );
    await tester.tap(find.text('etiquetas'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Da comanda'), '10');
    await tester.enterText(
      find.widgetWithText(TextField, 'Até a comanda'),
      '13',
    );
    await tester.tap(find.text('Continuar'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Imprimir'));
  }

  String texto(WidgetTester tester, String prefixo) => tester
      .widgetList<Text>(find.byType(Text))
      .map((t) => t.data ?? '')
      .firstWhere((t) => t.startsWith(prefixo));

  testWidgets('imprime as cadastradas em ordem e diz quais ficaram de fora', (
    tester,
  ) async {
    impressas = [];
    await pedirLote(
      tester,
      (job, _) async => impressas.add('${job['payload']['text_content']}'),
    );
    await tester.pumpAndSettle();

    expect(impressas, ['10', '11', '13']);
    expect(texto(tester, 'recado:'), contains('3 etiquetas impressas'));
    expect(texto(tester, 'recado:'), contains('ficaram de fora: 12'));
  });

  testWidgets('impressora falha no meio: para e diz de onde continuar', (
    tester,
  ) async {
    impressas = [];
    await pedirLote(tester, (job, _) async {
      final numero = '${job['payload']['text_content']}';
      if (numero == '11') throw StateError('sem papel');
      impressas.add(numero);
    });
    await tester.pumpAndSettle();

    expect(impressas, ['10']);
    final erro = texto(tester, 'erro:');
    expect(erro, contains('Parou na comanda 11'));
    expect(erro, contains('sem papel'));
    expect(erro, contains('imprima de 11 a 13'));
  });

  testWidgets('Parar interrompe antes da próxima etiqueta', (tester) async {
    impressas = [];
    final primeira = Completer<void>();
    await pedirLote(tester, (job, _) async {
      impressas.add('${job['payload']['text_content']}');
      if (impressas.length == 1) await primeira.future;
    });
    await tester.pump();
    await tester.pump();

    await tester.tap(find.text('Parar'));
    primeira.complete();
    await tester.pumpAndSettle();

    expect(impressas, ['10']);
    expect(texto(tester, 'recado:'), contains('Parado antes da comanda 11'));
  });
}
