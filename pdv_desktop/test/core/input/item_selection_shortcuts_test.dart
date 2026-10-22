import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_input_router.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_screen.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';
import 'package:starchef_pdv_desktop/core/input/scanner_keyboard_capture.dart';

/// As teclas que agem sobre UM item — e o Enter que confirma a tela.
///
/// Todas dependem de um alvo: sem pedido aberto elas não podem disparar, e sob
/// um diálogo elas pertencem a quem está na frente do operador.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime now;
  late PdvInputContext context;
  late PdvInputRouter router;
  late List<PdvShortcut> fired;

  KeyEvent keyOf(LogicalKeyboardKey key) => KeyDownEvent(
    physicalKey: PhysicalKeyboardKey.keyA,
    logicalKey: key,
    timeStamp: Duration.zero,
  );

  setUp(() {
    now = DateTime(2026, 1, 1, 12);
    context = const PdvInputContext(screen: PdvScreen.order, hasOrder: true);
    fired = [];
    router = PdvInputRouter(
      readContext: () => context,
      capture: ScannerKeyboardCapture(clock: () => now),
      readClipboard: () async => '',
    );
    router.shortcuts.listen(fired.add);
  });

  tearDown(() => router.dispose());

  Future<List<String>> press(List<LogicalKeyboardKey> keys) async {
    for (final key in keys) {
      router.handleKeyEvent(keyOf(key));
    }
    await Future<void>.delayed(Duration.zero);
    return fired.map((item) => item.id).toList();
  }

  // ── seleção ──────────────────────────────────────────────────────────

  test('as setas andam pela grade de produtos e o Espaço adiciona', () async {
    final ids = await press([
      LogicalKeyboardKey.arrowDown,
      LogicalKeyboardKey.arrowRight,
      LogicalKeyboardKey.space,
    ]);

    expect(ids, [
      PdvAction.gridDown,
      PdvAction.gridRight,
      PdvAction.addHighlighted,
    ]);
  });

  test('Shift + setas navegam entre os itens do carrinho', () {
    PdvShortcut atalho(String id) =>
        PdvShortcuts.all.firstWhere((item) => item.id == id);

    for (final (id, tecla) in [
      (PdvAction.moveSelectionDown, LogicalKeyboardKey.arrowDown),
      (PdvAction.moveSelectionUp, LogicalKeyboardKey.arrowUp),
    ]) {
      expect(atalho(id).trigger.key, tecla);
      expect(atalho(id).trigger.shift, isTrue, reason: id);
    }
    // E vêm ANTES das setas da grade: `matches` aceita o Shift a mais.
    final ordem = PdvShortcuts.all.map((item) => item.id).toList();
    expect(
      ordem.indexOf(PdvAction.moveSelectionDown),
      lessThan(ordem.indexOf(PdvAction.gridDown)),
    );
  });

  test('as setas não valem fora da edição do pedido', () async {
    context = const PdvInputContext(screen: PdvScreen.orders, hasOrder: true);

    expect(await press([LogicalKeyboardKey.arrowDown]), isEmpty);
  });

  test('+ e - agem sobre o item, no teclado normal e no numérico', () async {
    final ids = await press([
      LogicalKeyboardKey.add,
      LogicalKeyboardKey.numpadAdd,
      LogicalKeyboardKey.minus,
      LogicalKeyboardKey.numpadSubtract,
    ]);

    expect(ids, [
      PdvAction.increaseQuantity,
      PdvAction.increaseQuantity,
      PdvAction.decreaseQuantity,
      PdvAction.decreaseQuantity,
    ]);
  });

  test('sem pedido, nenhuma tecla de item dispara', () async {
    context = const PdvInputContext(screen: PdvScreen.order);

    final ids = await press([
      LogicalKeyboardKey.add,
      LogicalKeyboardKey.minus,
      LogicalKeyboardKey.delete,
    ]);

    expect(ids, isEmpty);
  });

  test('Delete tem proteção contra tecla presa', () async {
    final ids = await press(List.filled(4, LogicalKeyboardKey.delete));

    // Uma tecla que apaga nunca pode agir duas vezes por repetição automática.
    expect(ids, [PdvAction.removeItem]);
  });

  // ── Enter ────────────────────────────────────────────────────────────

  test('na venda, Enter vai ao pagamento', () async {
    expect(await press([LogicalKeyboardKey.enter]), [PdvAction.payment]);
  });

  test('Enter paga e Tab leva à pesquisa do catálogo', () async {
    expect(await press([LogicalKeyboardKey.enter, LogicalKeyboardKey.tab]), [
      PdvAction.payment,
      PdvAction.focusSearch,
    ]);
  });

  test(
    'a barra NAO e atalho: o leitor de comanda a digita no meio do QR',
    () async {
      // Um QR com endereço ("https://.../c/12") chega como teclas; a "/" no
      // meio levava o cursor à busca e o resto do código caía nela, travando
      // a leitura da comanda.
      expect(await press([LogicalKeyboardKey.slash]), isEmpty);
    },
  );

  test(
    'Enter não é confirmação nas telas que não têm ação principal',
    () async {
      for (final screen in [
        PdvScreen.home,
        PdvScreen.orders,
        PdvScreen.cash,
        PdvScreen.settings,
      ]) {
        context = PdvInputContext(screen: screen, hasOrder: true);
        router.handleKeyEvent(keyOf(LogicalKeyboardKey.enter));
      }
      await Future<void>.delayed(Duration.zero);

      expect(fired, isEmpty);
    },
  );

  test('dentro de um campo, o Enter é do campo', () async {
    context = const PdvInputContext(
      screen: PdvScreen.order,
      hasOrder: true,
      hasTextFocus: true,
    );

    expect(await press([LogicalKeyboardKey.enter]), isEmpty);
  });

  test('sob um diálogo, o Enter é do diálogo', () async {
    context = const PdvInputContext(
      screen: PdvScreen.payment,
      hasOrder: true,
      hasModal: true,
    );

    expect(await press([LogicalKeyboardKey.enter]), isEmpty);
  });

  test('Enter segurado não abre o pagamento duas vezes', () async {
    final ids = await press(List.filled(5, LogicalKeyboardKey.enter));

    // É a tecla mais fácil de segurar sem perceber, então uma inclusão ou um
    // recebimento nunca pode duplicar.
    expect(ids, [PdvAction.payment]);
  });

  test('o Enter do leitor não vira confirmação', () async {
    // Uma leitura rápida terminada em Enter: o terminador é consumido pela
    // captura antes de qualquer atalho.
    for (final character in '7891000100103'.split('')) {
      now = now.add(const Duration(milliseconds: 10));
      router.handleKeyEvent(
        KeyDownEvent(
          physicalKey: PhysicalKeyboardKey.keyA,
          logicalKey: LogicalKeyboardKey(character.codeUnitAt(0)),
          character: character,
          timeStamp: Duration.zero,
        ),
      );
    }
    now = now.add(const Duration(milliseconds: 10));
    router.handleKeyEvent(keyOf(LogicalKeyboardKey.enter));
    await Future<void>.delayed(Duration.zero);

    expect(fired, isEmpty);
  });

  // ── a ajuda acompanha o registro ─────────────────────────────────────

  test('as novas teclas aparecem na ajuda da edição do pedido', () {
    final labels = PdvShortcuts.forScreen(
      PdvScreen.order,
    ).map((item) => item.keysLabel).toList();

    expect(
      labels,
      containsAll(['Seta ↑', 'Seta ↓', '+', '-', 'Delete', 'Enter']),
    );
  });

  test('e não aparecem onde não valem', () {
    final labels = PdvShortcuts.forScreen(
      PdvScreen.cash,
    ).map((item) => item.keysLabel).toList();

    expect(labels, isNot(contains('Delete')));
    expect(labels, isNot(contains('Enter')));
  });
}
