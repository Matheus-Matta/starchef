import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

/// Verificação OFFLINE da senha de ações do caixa contra o hash do Django
/// (`pbkdf2_sha256$iterations$salt$base64hash`). O texto puro nunca é
/// armazenado — só o hash, guardado com segurança no dispositivo.
class CashPassword {
  const CashPassword._();

  /// Confere [password] contra o [encoded] (hash do Django). Roda em um isolate
  /// (`compute`) porque o PBKDF2 pode ter centenas de milhares de iterações e
  /// travaria a UI na thread principal.
  static Future<bool> verify(String password, String encoded) {
    if (password.isEmpty || encoded.isEmpty) return Future<bool>.value(false);
    return compute(_verifyInIsolate, <String, String>{
      'password': password,
      'encoded': encoded,
    });
  }
}

bool _verifyInIsolate(Map<String, String> args) {
  final password = args['password'] ?? '';
  final encoded = args['encoded'] ?? '';
  final parts = encoded.split(r'$');
  if (parts.length != 4 || parts[0] != 'pbkdf2_sha256') return false;

  final iterations = int.tryParse(parts[1]) ?? 0;
  final salt = parts[2];
  final expected = parts[3];
  if (iterations <= 0) return false;

  final derived = _pbkdf2Sha256(
    utf8.encode(password),
    utf8.encode(salt),
    iterations,
    32, // dklen = tamanho do digest do SHA-256
  );
  return _constantTimeEquals(base64.encode(derived), expected);
}

/// PBKDF2-HMAC-SHA256 com um único bloco (dklen == tamanho do digest).
Uint8List _pbkdf2Sha256(
  List<int> password,
  List<int> salt,
  int iterations,
  int dkLen,
) {
  final hmac = Hmac(sha256, password);
  final block = Uint8List(salt.length + 4)
    ..setRange(0, salt.length, salt)
    ..[salt.length + 3] = 1; // INT_32_BE(1) — índice do bloco

  var u = Uint8List.fromList(hmac.convert(block).bytes);
  final t = Uint8List.fromList(u);
  for (var i = 1; i < iterations; i++) {
    u = Uint8List.fromList(hmac.convert(u).bytes);
    for (var j = 0; j < t.length; j++) {
      t[j] ^= u[j];
    }
  }
  return Uint8List.sublistView(t, 0, dkLen);
}

bool _constantTimeEquals(String a, String b) {
  if (a.length != b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) {
    diff |= a.codeUnitAt(i) ^ b.codeUnitAt(i);
  }
  return diff == 0;
}
