import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_input_router.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_screen.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';

/// No pagamento, o teclado físico digita o valor como o teclado da tela.
///
/// Para trocar o valor o caixa precisava clicar no campo, apagar e digitar.
/// Agora os números (de cima e do numérico) entram direto no valor, Backspace
/// apaga o último e Delete zera — dentro de um campo (cupom, CPF), os números
/// continuam sendo do campo.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  String? acao(LogicalKeyboardKey key, {PdvScreen tela = PdvScreen.payment}) =>
      PdvShortcuts.resolve(
        KeyDownEvent(
          physicalKey: PhysicalKeyboardKey.keyA,
          logicalKey: key,
          timeStamp: Duration.zero,
        ),
        screen: tela,
      )?.id;

  test('números e numérico digitam o valor', () {
    expect(acao(LogicalKeyboardKey.digit7), 'payment-key:7');
    expect(acao(LogicalKeyboardKey.numpad0), 'payment-key:0');
  });

  test('Backspace apaga um dígito e Delete zera', () {
    expect(acao(LogicalKeyboardKey.backspace), 'payment-key:back');
    expect(acao(LogicalKeyboardKey.delete), 'payment-key:clear');
  });

  test('fora do pagamento os números não fazem nada', () {
    expect(acao(LogicalKeyboardKey.digit7, tela: PdvScreen.order), isNull);
  });

  test('com o cursor num campo, o número é do campo', () {
    const comCampo = PdvInputContext(
      screen: PdvScreen.payment,
      hasOrder: true,
      hasTextFocus: true,
    );
    final digito = PdvShortcuts.resolve(
      KeyDownEvent(
        physicalKey: PhysicalKeyboardKey.keyA,
        logicalKey: LogicalKeyboardKey.digit7,
        timeStamp: Duration.zero,
      ),
      screen: PdvScreen.payment,
    )!;

    expect(comCampo.shortcutEnabled(digito), isFalse);
  });
}
