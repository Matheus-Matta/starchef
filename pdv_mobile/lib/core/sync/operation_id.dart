import 'dart:convert';
import 'dart:math';

abstract final class OperationId {
  static final _random = Random.secure();

  static String random() {
    final bytes = List<int>.generate(18, (_) => _random.nextInt(256));
    return base64UrlEncode(bytes).replaceAll('=', '');
  }
}
