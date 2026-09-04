import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/input/pdv_input_router.dart';
import 'package:starchef_pdv/core/input/pdv_screen.dart';
import 'package:starchef_pdv/core/input/pdv_shortcuts.dart';
import 'package:starchef_pdv/core/input/scanner_keyboard_capture.dart';

/// A ordem de prioridade da entrada, que é o que evita o acidente clássico:
/// o Enter que o leitor envia no fim de um código confirmando um pagamento.
///
/// 1. campo de texto ou modal aberto;
/// 2. captura do leitor (que consome o próprio terminador);
/// 3. atalhos da página;
/// 4. atalhos globais.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime now;
  late PdvInputContext context;
  late PdvInputRouter router;
  late List<ScannedCode> codes;
  late List<PdvShortcut> shortcuts;
  String clipboard = '';

  KeyEvent keyOf(String character, {LogicalKeyboardKey? key}) => KeyDownEvent(
    physicalKey: PhysicalKeyboardKey.keyA,
    logicalKey: key ?? LogicalKeyboardKey(character.codeUnitAt(0)),
    character: key == null ? character : null,
    timeStamp: Duration.zero,
  );

  void typeFast(String code) {
    for (final character in code.split('')) {
      now = now.add(const Duration(milliseconds: 10));
      router.handleKeyEvent(keyOf(character));
    }
  }

  bool pressEnter() {
    now = now.add(const Duration(milliseconds: 10));
    return router.handleKeyEvent(keyOf('\n', key: LogicalKeyboardKey.enter));
  }

  setUp(() {
    now = DateTime(2026, 1, 1, 12);
    context = const PdvInputContext(screen: PdvScreen.order, hasOrder: true);
    codes = [];
    shortcuts = [];
    clipboard = '';
    router = PdvInputRouter(
      readContext: () => context,
      capture: ScannerKeyboardCapture(clock: () => now),
      readClipboard: () async => clipboard,
    );
    router.codes.listen(codes.add);
    router.shortcuts.listen(shortcuts.add);
  });

  tearDown(() => router.dispose());

  // ── prioridade ───────────────────────────────────────────────────────

  test('o Enter do leitor é consumido e não vira confirmação', () async {
    typeFast('7891000100103');
    final consumed = pressEnter();
    await Future<void>.delayed(Duration.zero);

    expect(consumed, isTrue, reason: 'o Enter não pode chegar à tela');
    expect(codes.single.value, '7891000100103');
    expect(codes.single.source, CodeSource.keyboardWedge);
    expect(shortcuts, isEmpty);
  });

  test('com um campo focado, o leitor não captura nada', () async {
    context = const PdvInputContext(
      screen: PdvScreen.order,
      hasOrder: true,
      hasTextFocus: true,
    );

    typeFast('7891000100103');
    final consumed = pressEnter();
    await Future<void>.delayed(Duration.zero);

    // O teclado pertence ao campo: nem o código nem o Enter são interceptados.
    expect(consumed, isFalse);
    expect(codes, isEmpty);
  });

  test('modal aberto bloqueia a captura, salvo quando ele aceita', () async {
    context = const PdvInputContext(screen: PdvScreen.order, hasModal: true);
    typeFast('7891000100103');
    expect(pressEnter(), isFalse);

    context = const PdvInputContext(
      screen: PdvScreen.order,
      hasModal: true,
      modalAcceptsScanner: true,
    );
    typeFast('7891000100103');
    expect(pressEnter(), isTrue);
    await Future<void>.delayed(Duration.zero);

    expect(codes.single.value, '7891000100103');
  });

  test('as telas que não leem código ignoram o leitor', () async {
    for (final screen in [PdvScreen.payment, PdvScreen.cash, PdvScreen.settings]) {
      context = PdvInputContext(screen: screen);
      typeFast('7891000100103');
      pressEnter();
    }
    await Future<void>.delayed(Duration.zero);

    // Nenhuma leitura nasce nessas telas — um código lido por engano no
    // pagamento ou no caixa não pode disparar coisa alguma.
    expect(codes, isEmpty);
  });

  test('nas telas sem ação principal, o Enter não é consumido', () async {
    // Sem nada para confirmar, a tecla pertence ao que estiver em foco.
    for (final screen in [PdvScreen.cash, PdvScreen.settings, PdvScreen.home]) {
      context = PdvInputContext(screen: screen);
      expect(pressEnter(), isFalse, reason: screen.label);
    }
  });

  // ── atalhos ──────────────────────────────────────────────────────────

  test('uma tecla de função dispara o atalho', () async {
    router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.f1));
    await Future<void>.delayed(Duration.zero);

    expect(shortcuts.single.id, PdvAction.help);
  });

  test('atalho que exige pedido fica inerte sem pedido', () async {
    context = const PdvInputContext(screen: PdvScreen.order);

    router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.f9));
    await Future<void>.delayed(Duration.zero);

    expect(shortcuts, isEmpty);
  });

  test('atalho de item não existe fora da edição do pedido', () async {
    context = const PdvInputContext(screen: PdvScreen.home, hasOrder: true);

    router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.delete));
    await Future<void>.delayed(Duration.zero);

    expect(shortcuts, isEmpty);
  });

  test('com campo focado, só teclas de função e combinações passam', () async {
    context = const PdvInputContext(
      screen: PdvScreen.order,
      hasOrder: true,
      hasTextFocus: true,
    );

    // F8 continua valendo: o operador não perde a leitura enquanto digita.
    router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.f8));
    // `+` pertence ao campo.
    router.handleKeyEvent(keyOf('+', key: LogicalKeyboardKey.add));
    await Future<void>.delayed(Duration.zero);

    expect(shortcuts.map((item) => item.id), [PdvAction.readClipboard]);
  });

  test('nenhum atalho dispara por baixo de um modal', () async {
    context = const PdvInputContext(
      screen: PdvScreen.order,
      hasOrder: true,
      hasModal: true,
    );

    // Esc precisa fechar o modal e parar aí: se o roteador respondesse
    // também, uma tecla fecharia o diálogo E voltaria de página.
    router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.escape));
    router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.f10));
    await Future<void>.delayed(Duration.zero);

    expect(shortcuts, isEmpty);
  });

  test('tecla presa não dispara duas vezes o que cobra ou imprime', () async {
    for (var index = 0; index < 5; index++) {
      router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.f10));
    }
    await Future<void>.delayed(Duration.zero);

    // Repetição automática de tecla não pode virar duas cobranças.
    expect(shortcuts.length, 1);
  });

  test('a mesma proteção não atrapalha um atalho inofensivo', () async {
    for (var index = 0; index < 3; index++) {
      router.handleKeyEvent(keyOf('', key: LogicalKeyboardKey.f1));
    }
    await Future<void>.delayed(Duration.zero);

    expect(shortcuts.length, 3);
  });

  // ── área de transferência ────────────────────────────────────────────

  test('o texto colado é tratado como uma leitura', () async {
    clipboard = '  7891000100103\n';

    final accepted = await router.readFromClipboard();
    await Future<void>.delayed(Duration.zero);

    expect(accepted, isTrue);
    expect(codes.single.value, '7891000100103');
    expect(codes.single.source, CodeSource.clipboard);
  });

  test('um texto qualquer colado não vira código', () async {
    for (final text in [
      'a senha é 12345',
      'linha um\nlinha dois',
      '',
      '   ',
    ]) {
      clipboard = text;
      expect(await router.readFromClipboard(), isFalse, reason: text);
    }
    await Future<void>.delayed(Duration.zero);

    expect(codes, isEmpty);
  });

  // ── normalização ─────────────────────────────────────────────────────

  test('a normalização preserva zeros à esquerda', () {
    expect(PdvInputRouter.normalize(' 0000012345670 \r\n'), '0000012345670');
  });

  test('a leitura serial passa pelo mesmo caminho', () async {
    final accepted = router.submit('789100010010 3\n', source: CodeSource.serial);
    final valid = router.submit('7891000100103\r\n', source: CodeSource.serial);
    await Future<void>.delayed(Duration.zero);

    // Espaço no meio não é código.
    expect(accepted, isFalse);
    expect(valid, isTrue);
    expect(codes.single.source, CodeSource.serial);
  });

  test('a balança mantém a interpretação própria', () async {
    context = const PdvInputContext(screen: PdvScreen.scale);

    expect(router.submit('7891000100103', source: CodeSource.serial), isFalse);
    // E o roteador também não consome as teclas lá: se consumisse, a captura
    // própria da balança pararia de receber a leitura que ela sabe ler.
    typeFast('7891000100103');
    expect(pressEnter(), isFalse);
    await Future<void>.delayed(Duration.zero);

    expect(codes, isEmpty);
  });
}
