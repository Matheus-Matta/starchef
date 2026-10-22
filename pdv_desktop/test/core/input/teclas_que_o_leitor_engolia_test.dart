import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_input_router.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_screen.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';
import 'package:starchef_pdv_desktop/core/input/scanner_keyboard_capture.dart';

/// Espaço, + e − na venda, COM o caractere que o teclado de verdade manda.
///
/// Na venda o leitor de código fica ligado e guardava TODO caractere como
/// começo de leitura: o Espaço (adicionar o produto) e o + / − (quantidade)
/// sumiam no buffer. Os testes antigos mandavam a tecla sem caractere e não
/// viam isso. Sem leitura em andamento, essas teclas são atalho; no meio de
/// uma leitura rápida, continuam sendo do código.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime agora;
  late List<String> atalhos;
  late List<String> codigos;
  late PdvInputRouter router;

  setUp(() {
    agora = DateTime(2026, 1, 1, 12);
    atalhos = [];
    codigos = [];
    router = PdvInputRouter(
      readContext: () =>
          const PdvInputContext(screen: PdvScreen.order, hasOrder: true),
      capture: ScannerKeyboardCapture(clock: () => agora),
      readClipboard: () async => '',
    );
    router.shortcuts.listen((a) => atalhos.add(a.id));
    router.codes.listen((c) => codigos.add(c.value));
  });

  tearDown(() => router.dispose());

  bool tecla(LogicalKeyboardKey key, String caractere) {
    agora = agora.add(const Duration(milliseconds: 10));
    return router.handleKeyEvent(
      KeyDownEvent(
        physicalKey: PhysicalKeyboardKey.keyA,
        logicalKey: key,
        character: caractere,
        timeStamp: Duration.zero,
      ),
    );
  }

  test('Espaço, + e − viram atalho', () async {
    tecla(LogicalKeyboardKey.space, ' ');
    agora = agora.add(const Duration(seconds: 1));
    tecla(LogicalKeyboardKey.add, '+');
    agora = agora.add(const Duration(seconds: 1));
    tecla(LogicalKeyboardKey.minus, '-');
    await Future<void>.delayed(Duration.zero);

    expect(atalhos, [
      PdvAction.addHighlighted,
      PdvAction.increaseQuantity,
      PdvAction.decreaseQuantity,
    ]);
  });

  test('no meio de uma leitura rápida, o − é do código', () async {
    for (final c in 'AB-12'.split('')) {
      tecla(LogicalKeyboardKey(c.codeUnitAt(0)), c);
    }
    tecla(LogicalKeyboardKey.enter, '\n');
    await Future<void>.delayed(Duration.zero);

    expect(codigos, ['AB-12']);
    expect(atalhos, isEmpty);
  });
}
