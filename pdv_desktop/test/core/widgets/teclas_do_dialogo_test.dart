import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/widgets/teclas_do_dialogo.dart';

/// Em todo diálogo: Enter confirma, Esc cancela.
///
/// Desde que Enter e Espaço pararam de "clicar" o botão focado
/// (`teclado_sem_navegacao.dart`), um diálogo só se fechava com o mouse —
/// alguns sem botão nenhum de confirmação ao alcance do teclado.
void main() {
  late List<String> gestos;

  Future<void> abrir(
    WidgetTester tester,
    List<Widget> Function(BuildContext) acoes,
  ) async {
    gestos = [];
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showDialog<void>(
              context: context,
              builder: (dialogo) {
                final lista = acoes(dialogo);
                return TeclasDoDialogo(
                  acoes: lista,
                  child: AlertDialog(
                    content: const Text('Descartar?'),
                    actions: lista,
                  ),
                );
              },
            ),
            child: const Text('abrir'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
  }

  List<Widget> Function(BuildContext) padrao() =>
      (dialogo) => [
        TextButton(
          onPressed: () {
            gestos.add('cancelar');
            Navigator.pop(dialogo);
          },
          child: const Text('Voltar'),
        ),
        FilledButton(
          onPressed: () {
            gestos.add('confirmar');
            Navigator.pop(dialogo);
          },
          child: const Text('Descartar'),
        ),
      ];

  testWidgets('Enter aciona o botão principal', (tester) async {
    await abrir(tester, padrao());

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(gestos, ['confirmar']);
    expect(find.text('Descartar?'), findsNothing);
  });

  testWidgets('Esc aciona o cancelar', (tester) async {
    await abrir(tester, padrao());

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();

    expect(gestos, ['cancelar']);
  });

  testWidgets('sem botão de cancelar, Esc só fecha', (tester) async {
    await abrir(
      tester,
      (dialogo) => [
        FilledButton(
          onPressed: () => gestos.add('ok'),
          child: const Text('Ok'),
        ),
      ],
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();

    expect(gestos, isEmpty);
    expect(find.text('Descartar?'), findsNothing);
  });

  testWidgets('botão principal desligado: Enter não faz nada', (tester) async {
    await abrir(
      tester,
      (dialogo) => [
        TextButton(onPressed: () {}, child: const Text('Voltar')),
        const FilledButton(onPressed: null, child: Text('Salvar')),
      ],
    );

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(find.text('Descartar?'), findsOneWidget);
  });
}
