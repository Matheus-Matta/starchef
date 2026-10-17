import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_input_router.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_key_barrier.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_screen.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';

/// Na tela de pagamento, com o sino de notificações focado pelo Tab, um Enter
/// registrava o recebimento (atalho) E abria as notificações (botão focado).
void main() {
  late PdvInputRouter router;
  late List<String> atalhos;
  late int cliques;
  late FocusNode foco;

  setUp(() {
    router = PdvInputRouter(
      readContext: () =>
          const PdvInputContext(screen: PdvScreen.payment, hasOrder: true),
    );
    atalhos = [];
    router.shortcuts.listen((atalho) => atalhos.add(atalho.id));
    HardwareKeyboard.instance.addHandler(router.handleKeyEvent);
    cliques = 0;
    foco = FocusNode();
  });

  tearDown(() {
    HardwareKeyboard.instance.removeHandler(router.handleKeyEvent);
    router.dispose();
    foco.dispose();
  });

  Widget sino() => Scaffold(
    body: IconButton(
      focusNode: foco,
      onPressed: () => cliques++,
      icon: const Icon(Icons.notifications_outlined),
    ),
  );

  testWidgets('com a barreira, Enter vira só o atalho', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PdvKeyBarrier(router: router, child: sino()),
      ),
    );
    foco.requestFocus();
    await tester.pump();

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();

    expect(atalhos, [PdvAction.confirm]);
    expect(cliques, 0);
  });

  testWidgets('sem a barreira, o mesmo Enter fazia as duas coisas', (
    tester,
  ) async {
    await tester.pumpWidget(MaterialApp(home: sino()));
    foco.requestFocus();
    await tester.pump();

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();

    expect(atalhos, [PdvAction.confirm]);
    expect(cliques, 1);
  });

  testWidgets('tecla que o roteador não usa continua chegando ao foco', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: PdvKeyBarrier(router: router, child: sino()),
      ),
    );
    foco.requestFocus();
    await tester.pump();

    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pump();

    expect(atalhos, isEmpty);
    expect(cliques, 1);
  });
}
