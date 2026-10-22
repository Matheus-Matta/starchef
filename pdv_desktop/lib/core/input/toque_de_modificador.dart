import 'package:flutter/services.dart';

/// Ctrl ou Shift apertado e SOLTO sozinho, sem outra tecla no meio.
///
/// É o que troca a categoria na venda (Ctrl a seguinte, Shift a anterior). O
/// toque só existe na soltura: Ctrl + E, Shift + ↓ e o Shift da letra
/// maiúscula passam por outra tecla antes, e não contam.
class ToqueDeModificador {
  String? _pendente;

  static final _controles = {
    LogicalKeyboardKey.controlLeft,
    LogicalKeyboardKey.controlRight,
    LogicalKeyboardKey.control,
  };
  static final _shifts = {
    LogicalKeyboardKey.shiftLeft,
    LogicalKeyboardKey.shiftRight,
    LogicalKeyboardKey.shift,
  };

  /// `'ctrl'` ou `'shift'` quando este evento fecha um toque sozinho.
  String? ler(KeyEvent event) {
    final grupo = _grupo(event.logicalKey);
    if (event is KeyDownEvent) {
      _pendente = grupo;
      return null;
    }
    if (event is KeyRepeatEvent) {
      // Segurar Ctrl não é tocar Ctrl.
      _pendente = null;
      return null;
    }
    if (event is KeyUpEvent && grupo != null && grupo == _pendente) {
      _pendente = null;
      return grupo;
    }
    return null;
  }

  static String? _grupo(LogicalKeyboardKey key) {
    if (_controles.contains(key)) return 'ctrl';
    if (_shifts.contains(key)) return 'shift';
    return null;
  }
}
