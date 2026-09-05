import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

/// Assinatura do relay da rede local.
///
/// É a MESMA função do PDV desktop
/// (`flutter/lib/features/topology/services/local_topology_service.dart`,
/// `LocalRelayAuthenticator`). Qualquer divergência aqui — ordem dos campos,
/// separador, codificação — faz o Caixa Principal recusar tudo com 401 sem
/// dizer por quê, então este arquivo é uma cópia deliberada e tem teste
/// próprio travando os vetores.
abstract final class RelaySignature {
  static String request({
    required String secret,
    required String method,
    required String path,
    required int timestamp,
    required String nonce,
    required String account,
    required String actor,
    required String restaurant,
    required String nodeId,
    required String body,
  }) => _digest(secret, [
    method.toUpperCase(),
    path,
    '$timestamp',
    nonce,
    account,
    actor,
    restaurant,
    nodeId,
    body,
  ]);

  static String response({
    required String secret,
    required String requestNonce,
    required int statusCode,
    required String body,
  }) => _digest(secret, ['RESPONSE', requestNonce, '$statusCode', body]);

  static String _digest(String secret, List<String> parts) {
    final canonical = parts.join('\n');
    final digest = Hmac(
      sha256,
      utf8.encode(secret),
    ).convert(utf8.encode(canonical));
    return base64UrlEncode(digest.bytes).replaceAll('=', '');
  }

  static bool constantTimeEquals(String left, String right) {
    final a = utf8.encode(left);
    final b = utf8.encode(right);
    var difference = a.length ^ b.length;
    final length = a.length > b.length ? a.length : b.length;
    for (var index = 0; index < length; index++) {
      final av = index < a.length ? a[index] : 0;
      final bv = index < b.length ? b[index] : 0;
      difference |= av ^ bv;
    }
    return difference == 0;
  }

  /// Nonce/identificador de nó no mesmo formato do PDV: 32 bytes em base64url
  /// sem padding (o principal exige no mínimo 8 caracteres).
  static String randomId([Random? random]) {
    final source = random ?? Random.secure();
    final bytes = List<int>.generate(24, (_) => source.nextInt(256));
    return base64UrlEncode(bytes).replaceAll('=', '');
  }
}
