import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/toque_de_modificador.dart';

/// Ctrl e Shift tocados SOZINHOS trocam a categoria; com outra tecla no meio
/// (Ctrl + E, Shift + ↓, Shift da maiúscula) não.
void main() {
  KeyEvent desce(LogicalKeyboardKey k) => KeyDownEvent(
    physicalKey: PhysicalKeyboardKey.keyA,
    logicalKey: k,
    timeStamp: Duration.zero,
  );
  KeyEvent sobe(LogicalKeyboardKey k) => KeyUpEvent(
    physicalKey: PhysicalKeyboardKey.keyA,
    logicalKey: k,
    timeStamp: Duration.zero,
  );

  test('Ctrl sozinho é a seguinte, Shift sozinho a anterior', () {
    final toque = ToqueDeModificador();

    expect(toque.ler(desce(LogicalKeyboardKey.controlLeft)), isNull);
    expect(toque.ler(sobe(LogicalKeyboardKey.controlLeft)), 'ctrl');
    toque.ler(desce(LogicalKeyboardKey.shiftRight));
    expect(toque.ler(sobe(LogicalKeyboardKey.shiftRight)), 'shift');
  });

  test('com outra tecla no meio não é toque', () {
    final toque = ToqueDeModificador();

    toque.ler(desce(LogicalKeyboardKey.controlLeft));
    toque.ler(desce(LogicalKeyboardKey.keyE));
    toque.ler(sobe(LogicalKeyboardKey.keyE));
    expect(toque.ler(sobe(LogicalKeyboardKey.controlLeft)), isNull);

    toque.ler(desce(LogicalKeyboardKey.shiftLeft));
    toque.ler(desce(LogicalKeyboardKey.arrowDown));
    expect(toque.ler(sobe(LogicalKeyboardKey.shiftLeft)), isNull);
  });
}
