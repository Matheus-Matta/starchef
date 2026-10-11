import 'dart:convert';
import 'dart:math';

abstract final class OperationId {
  static final _random = Random.secure();

  static String random() {
    final bytes = List<int>.generate(18, (_) => _random.nextInt(256));
    return base64UrlEncode(bytes).replaceAll('=', '');
  }

  /// UUID v4 — a identidade de um registro criado neste aparelho. Vai no
  /// corpo e fica guardado na fila: todo reenvio, na loja ou na nuvem, leva o
  /// MESMO, e a sincronização junta as cópias numa só.
  static String uuid() {
    final bytes = List<int>.generate(16, (_) => _random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // versão 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variante RFC 4122
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }
}
