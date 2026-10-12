import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_input_router.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_screen.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';
import 'package:starchef_pdv_desktop/core/input/scanner_keyboard_capture.dart';

/// Na tela de pagamento, ↑ e ↓ trocam a forma de pagamento.
///
/// Valem COM o cursor no campo do valor: ele é de uma linha só e não usa as
/// setas, e é onde o caixa está digitando. A exceção é o cupom, cuja lista de
/// opções anda pelas setas — ali elas continuam sendo do campo.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late PdvInputContext context;
  late PdvInputRouter router;
  late List<PdvShortcut> fired;

  setUp(() {
    context = const PdvInputContext(screen: PdvScreen.payment, hasOrder: true);
    fired = [];
    router = PdvInputRouter(
      readContext: () => context,
      capture: ScannerKeyboardCapture(clock: () => DateTime(2026)),
      readClipboard: () async => '',
    );
    router.shortcuts.listen(fired.add);
  });

  tearDown(() => router.dispose());

  Future<List<String>> press(List<LogicalKeyboardKey> keys) async {
    for (final key in keys) {
      router.handleKeyEvent(
        KeyDownEvent(
          physicalKey: PhysicalKeyboardKey.keyA,
          logicalKey: key,
          timeStamp: Duration.zero,
        ),
      );
    }
    await Future<void>.delayed(Duration.zero);
    return fired.map((item) => item.id).toList();
  }

  test('setas trocam a forma de pagamento', () async {
    final ids = await press([
      LogicalKeyboardKey.arrowDown,
      LogicalKeyboardKey.arrowUp,
    ]);

    expect(ids, [PdvAction.nextPaymentMethod, PdvAction.previousPaymentMethod]);
  });

  test('valem com o cursor no campo do valor', () async {
    context = const PdvInputContext(
      screen: PdvScreen.payment,
      hasOrder: true,
      hasTextFocus: true,
    );

    expect(await press([LogicalKeyboardKey.arrowDown]), [
      PdvAction.nextPaymentMethod,
    ]);
  });

  test('no cupom as setas sao da lista de opcoes', () async {
    context = const PdvInputContext(
      screen: PdvScreen.payment,
      hasOrder: true,
      hasTextFocus: true,
      textFieldOwnsArrows: true,
    );

    expect(await press([LogicalKeyboardKey.arrowDown]), isEmpty);
  });

  test('com um dialogo aberto as setas sao dele', () async {
    context = const PdvInputContext(
      screen: PdvScreen.payment,
      hasOrder: true,
      hasModal: true,
    );

    expect(await press([LogicalKeyboardKey.arrowDown]), isEmpty);
  });

  test('na tela do pedido as setas continuam andando nos itens', () async {
    context = const PdvInputContext(
      screen: PdvScreen.order,
      hasOrder: true,
      hasTextFocus: true,
    );

    // No pedido, com a busca focada, as setas seguem sendo do campo.
    expect(await press([LogicalKeyboardKey.arrowDown]), isEmpty);
  });
}
