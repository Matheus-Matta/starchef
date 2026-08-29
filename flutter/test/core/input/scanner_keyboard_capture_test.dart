import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/input/scanner_keyboard_capture.dart';

/// Um leitor USB é indistinguível de um teclado — exceto pela cadência.
///
/// É essa diferença que o buffer usa: o leitor manda o código inteiro em
/// milissegundos e termina com Enter. Sem consumir esse Enter, ele chegaria à
/// tela como uma tecla comum e confirmaria o que estivesse em foco: um
/// pagamento, um modal.
void main() {
  // `HardwareKeyboard.instance` (usado para ignorar atalhos) exige o binding.
  TestWidgetsFlutterBinding.ensureInitialized();

  late DateTime now;
  late ScannerKeyboardCapture capture;

  KeyEvent keyOf(String character, {LogicalKeyboardKey? key}) => KeyDownEvent(
    physicalKey: PhysicalKeyboardKey.keyA,
    logicalKey: key ?? LogicalKeyboardKey(character.codeUnitAt(0)),
    character: key == null ? character : null,
    timeStamp: Duration.zero,
  );

  /// Digita como um leitor: rápido e sem pausas.
  ScannerKeyResult scan(String code, {Duration gap = const Duration(milliseconds: 12)}) {
    for (final character in code.split('')) {
      now = now.add(gap);
      capture.handle(keyOf(character), acceptsInput: true);
    }
    now = now.add(gap);
    return capture.handle(
      keyOf('\n', key: LogicalKeyboardKey.enter),
      acceptsInput: true,
    );
  }

  setUp(() {
    now = DateTime(2026, 1, 1, 12);
    capture = ScannerKeyboardCapture(clock: () => now);
  });

  test('uma leitura rápida vira um código e consome o Enter', () {
    final result = scan('7891000100103');

    expect(result.code, '7891000100103');
    // O Enter não pode sobrar: solto, ele confirmaria a ação em foco.
    expect(result.consumed, isTrue);
  });

  test('as teclas do código não chegam à tela', () {
    now = now.add(const Duration(milliseconds: 10));
    final first = capture.handle(keyOf('7'), acceptsInput: true);

    expect(first.consumed, isTrue);
    expect(first.hasCode, isFalse);
    expect(capture.partial, '7');
  });

  test('Tab termina a leitura tanto quanto Enter', () {
    for (final character in '12345670'.split('')) {
      now = now.add(const Duration(milliseconds: 10));
      capture.handle(keyOf(character), acceptsInput: true);
    }
    now = now.add(const Duration(milliseconds: 10));

    final result = capture.handle(
      keyOf('\t', key: LogicalKeyboardKey.tab),
      acceptsInput: true,
    );

    expect(result.code, '12345670');
    expect(result.consumed, isTrue);
  });

  test('digitação humana não vira leitura', () {
    // Meio segundo entre teclas: ninguém confunde isso com um leitor.
    final result = scan('7891000100103', gap: const Duration(milliseconds: 500));

    expect(result.hasCode, isFalse);
    // E o Enter continua sendo do operador.
    expect(result.consumed, isFalse);
  });

  test('uma pausa no meio descarta o que veio antes', () {
    now = now.add(const Duration(milliseconds: 10));
    capture.handle(keyOf('1'), acceptsInput: true);
    now = now.add(const Duration(milliseconds: 10));
    capture.handle(keyOf('2'), acceptsInput: true);
    // Pausa longa: o que estava acumulado era digitação.
    now = now.add(const Duration(seconds: 3));
    capture.handle(keyOf('9'), acceptsInput: true);

    expect(capture.partial, '9');
  });

  test('Enter solto não é consumido', () {
    now = now.add(const Duration(milliseconds: 10));

    final result = capture.handle(
      keyOf('\n', key: LogicalKeyboardKey.enter),
      acceptsInput: true,
    );

    expect(result.consumed, isFalse);
    expect(result.hasCode, isFalse);
  });

  test('código curto demais não é leitura', () {
    final result = scan('12');

    expect(result.hasCode, isFalse);
    expect(result.consumed, isFalse);
  });

  test('o buffer tem teto de tamanho', () {
    final capture = ScannerKeyboardCapture(clock: () => now, maximumLength: 5);
    for (final character in '1234567890'.split('')) {
      now = now.add(const Duration(milliseconds: 5));
      capture.handle(keyOf(character), acceptsInput: true);
    }

    // Passou do teto: o buffer é descartado em vez de crescer sem limite.
    expect(capture.partial.length, lessThanOrEqualTo(5));
  });

  test('com um campo focado, nada é capturado', () {
    now = now.add(const Duration(milliseconds: 10));

    final result = capture.handle(keyOf('7'), acceptsInput: false);

    expect(result.consumed, isFalse);
    expect(capture.partial, isEmpty);
  });

  test('um atalho interrompe a leitura em vez de entrar nela', () async {
    now = now.add(const Duration(milliseconds: 10));
    capture.handle(keyOf('7'), acceptsInput: true);

    // Ctrl pressionado: é atalho, não código.
    await simulateKeyDownEvent(LogicalKeyboardKey.controlLeft);
    now = now.add(const Duration(milliseconds: 10));
    final result = capture.handle(keyOf('c'), acceptsInput: true);
    await simulateKeyUpEvent(LogicalKeyboardKey.controlLeft);

    expect(result.consumed, isFalse);
    expect(capture.partial, isEmpty);
  });
}
