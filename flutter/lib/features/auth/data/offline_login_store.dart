import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/security/cash_password.dart';
import '../../../core/storage/durable_secure_store.dart';
import '../domain/auth_session.dart';

abstract interface class OfflineLoginStore {
  Future<void> save({
    required String username,
    required String password,
    required AuthSession session,
  });

  Future<AuthSession?> authenticate({
    required String username,
    required String password,
  });
}

/// Cache de login protegido pelo cofre do sistema operacional.
///
/// A senha nunca é salva. O cofre recebe somente um verificador PBKDF2 com
/// salt aleatório e a última sessão autorizada pelo servidor. O nome do
/// usuário também não aparece na chave do cofre: usamos seu SHA-256.
class SecureOfflineLoginStore implements OfflineLoginStore {
  SecureOfflineLoginStore({
    FlutterSecureStorage? storage,
    SecureValueStore? valueStore,
    this.passwordIterations = 210000,
  }) : _storage =
           valueStore ??
           DurableSecureStore(
             primary: FlutterSecureValueStore(
               storage ?? const FlutterSecureStorage(),
             ),
           );

  static const _prefix = 'starchef_offline_login_v1_';
  final SecureValueStore _storage;
  final int passwordIterations;

  static String _normalizedUsername(String value) => value.trim().toLowerCase();

  static String _key(String username) {
    final normalized = _normalizedUsername(username);
    return '$_prefix${sha256.convert(utf8.encode(normalized))}';
  }

  @override
  Future<void> save({
    required String username,
    required String password,
    required AuthSession session,
  }) async {
    final normalized = _normalizedUsername(username);
    if (normalized.isEmpty || password.isEmpty) return;
    final passwordHash = await CashPassword.encode(
      password,
      iterations: passwordIterations,
    );
    await _storage.write(
      _key(normalized),
      jsonEncode({
        'username': normalized,
        'password_hash': passwordHash,
        'session': session.toJson(),
        'updated_at': DateTime.now().toUtc().toIso8601String(),
      }),
    );
  }

  @override
  Future<AuthSession?> authenticate({
    required String username,
    required String password,
  }) async {
    final normalized = _normalizedUsername(username);
    if (normalized.isEmpty || password.isEmpty) return null;
    try {
      final raw = await _storage.read(_key(normalized));
      if (raw == null) return null;
      final cached = jsonDecode(raw) as Map<String, dynamic>;
      if ('${cached['username'] ?? ''}' != normalized) return null;
      final matches = await CashPassword.verify(
        password,
        '${cached['password_hash'] ?? ''}',
      );
      if (!matches) return null;
      return AuthSession.fromJson(
        Map<String, dynamic>.from(cached['session'] as Map),
      );
    } catch (_) {
      // Cofre indisponível ou entrada corrompida equivale a cache ausente.
      return null;
    }
  }
}
