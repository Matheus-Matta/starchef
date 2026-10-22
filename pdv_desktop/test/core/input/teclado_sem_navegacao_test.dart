import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/teclado_sem_navegacao.dart';

/// Tab e setas não passeiam mais pelos botões; Enter e Espaço não "clicam" o
/// botão que ficou focado depois de um clique. O teclado do PDV são os
/// atalhos dele — o resto é mouse.
void main() {
  late List<String> cliques;
  late FocusNode primeiro;
  late TextEditingController texto;

  Future<void> montar(WidgetTester tester) async {
    cliques = [];
    primeiro = FocusNode();
    texto = TextEditingController(text: 'abc');
    addTearDown(primeiro.dispose);
    addTearDown(texto.dispose);
    await tester.pumpWidget(
      MaterialApp(
        shortcuts: atalhosSemNavegacao(),
        home: Scaffold(
          body: Column(
            children: [
              ElevatedButton(
                focusNode: primeiro,
                onPressed: () => cliques.add('primeiro'),
                child: const Text('Primeiro'),
              ),
              ElevatedButton(
                onPressed: () => cliques.add('segundo'),
                child: const Text('Segundo'),
              ),
              TextField(controller: texto),
            ],
          ),
        ),
      ),
    );
  }

  testWidgets('Tab e setas não tiram o foco do botão', (tester) async {
    await montar(tester);
    primeiro.requestFocus();
    await tester.pump();

    for (final tecla in [
      LogicalKeyboardKey.tab,
      LogicalKeyboardKey.arrowDown,
      LogicalKeyboardKey.arrowRight,
    ]) {
      await tester.sendKeyEvent(tecla);
      await tester.pump();
      expect(primeiro.hasFocus, isTrue, reason: '$tecla');
    }
  });

  testWidgets('Enter e Espaço não clicam o botão focado', (tester) async {
    await montar(tester);
    // O foco que o Tab dava ao botão (clicar com o mouse não foca).
    primeiro.requestFocus();
    await tester.pump();

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pump();

    expect(cliques, isEmpty);
  });

  testWidgets('no campo de texto a seta continua movendo o cursor', (
    tester,
  ) async {
    await montar(tester);
    await tester.tap(find.byType(TextField));
    await tester.pump();
    texto.selection = const TextSelection.collapsed(offset: 3);

    await tester.sendKeyEvent(LogicalKeyboardKey.arrowLeft);
    await tester.pump();

    expect(texto.selection.baseOffset, 2);
  });
}
