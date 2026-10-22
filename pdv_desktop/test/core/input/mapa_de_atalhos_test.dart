import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_input_router.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_screen.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';

/// O mapa de teclas: F1 a F8 são as páginas, Enter paga na venda, Ctrl + E
/// manda à cozinha, Ctrl + P imprime, Tab leva à busca.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  KeyEvent tecla(LogicalKeyboardKey key) => KeyDownEvent(
    physicalKey: PhysicalKeyboardKey.keyA,
    logicalKey: key,
    timeStamp: Duration.zero,
  );

  String? acao(LogicalKeyboardKey key, PdvScreen tela) =>
      PdvShortcuts.resolve(tecla(key), screen: tela)?.id;

  test('F1 a F8 abrem as páginas em qualquer tela', () {
    final paginas = {
      LogicalKeyboardKey.f1: PdvAction.goSale,
      LogicalKeyboardKey.f2: PdvAction.goOrders,
      LogicalKeyboardKey.f3: PdvAction.goTables,
      LogicalKeyboardKey.f4: PdvAction.goCommands,
      LogicalKeyboardKey.f5: PdvAction.goCustomers,
      LogicalKeyboardKey.f6: PdvAction.goCash,
      LogicalKeyboardKey.f7: PdvAction.goScale,
      LogicalKeyboardKey.f8: PdvAction.goSettings,
    };
    for (final tela in [PdvScreen.order, PdvScreen.payment, PdvScreen.orders]) {
      for (final entrada in paginas.entries) {
        expect(acao(entrada.key, tela), entrada.value, reason: tela.label);
      }
    }
  });

  test('F9 notificações, F10 caixa, F12 ajuda', () {
    expect(
      acao(LogicalKeyboardKey.f9, PdvScreen.order),
      PdvAction.notifications,
    );
    expect(acao(LogicalKeyboardKey.f10, PdvScreen.order), PdvAction.cashCenter);
    expect(acao(LogicalKeyboardKey.f12, PdvScreen.order), PdvAction.help);
  });

  test('Enter paga na venda e confirma no pagamento', () {
    expect(acao(LogicalKeyboardKey.enter, PdvScreen.order), PdvAction.payment);
    expect(
      acao(LogicalKeyboardKey.enter, PdvScreen.payment),
      PdvAction.confirm,
    );
  });

  test('nenhuma tecla faz duas coisas na mesma tela', () {
    // Com duas entradas para a mesma tecla, vale a primeira do catálogo — e
    // a segunda vira uma linha da ajuda que mente.
    for (final tela in PdvScreen.values) {
      final vistas = <String, String>{};
      for (final atalho in PdvShortcuts.forScreen(tela)) {
        final t = atalho.trigger;
        final chave = '${t.key.keyId}|${t.control}|${t.shift}|${t.alt}';
        final outra = vistas[chave];
        expect(
          outra,
          anyOf(isNull, atalho.id),
          reason: '${t.description} em ${tela.label}: $outra e ${atalho.id}',
        );
        vistas[chave] = atalho.id;
      }
    }
  });

  test('as etiquetas da tela leem a tecla do catálogo', () {
    expect(
      PdvShortcuts.teclaDe(PdvAction.payment, screen: PdvScreen.order),
      'Enter',
    );
    expect(PdvShortcuts.teclaDe(PdvAction.sendToKitchen), 'Ctrl + E');
    expect(PdvShortcuts.teclaDe(PdvAction.printReceipt), 'Ctrl + P');
    expect(PdvShortcuts.teclaDe(PdvAction.focusSearch), 'Tab');
  });

  test('Tab leva à busca até de dentro de outro campo', () {
    const comCampo = PdvInputContext(
      screen: PdvScreen.order,
      hasOrder: true,
      hasTextFocus: true,
    );
    final tab = PdvShortcuts.resolve(
      tecla(LogicalKeyboardKey.tab),
      screen: PdvScreen.order,
    )!;

    expect(tab.id, PdvAction.focusSearch);
    expect(comCampo.shortcutEnabled(tab), isTrue);
  });

  testWidgets('Ctrl + E manda à cozinha e Ctrl + P imprime', (tester) async {
    await simulateKeyDownEvent(LogicalKeyboardKey.controlLeft);

    expect(
      acao(LogicalKeyboardKey.keyE, PdvScreen.order),
      PdvAction.sendToKitchen,
    );
    expect(
      acao(LogicalKeyboardKey.keyP, PdvScreen.order),
      PdvAction.printReceipt,
    );

    await simulateKeyUpEvent(LogicalKeyboardKey.controlLeft);
  });
}
