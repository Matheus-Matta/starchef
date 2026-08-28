import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../features/auth/domain/auth_session.dart';
import 'durable_secure_store.dart';

abstract interface class SessionStore {
  Future<void> save(AuthSession session);
  Future<AuthSession?> read();
  Future<void> clear();
}

class SecureSessionStore implements SessionStore {
  SecureSessionStore({
    FlutterSecureStorage? storage,
    SecureValueStore? valueStore,
    AuthSession? initialSession,
  }) : _storage =
           valueStore ??
           DurableSecureStore(
             primary: FlutterSecureValueStore(
               storage ?? const FlutterSecureStorage(),
             ),
           ),
       _initialSession = initialSession;

  static const _accessKey = 'starchef_access_token';
  static const _refreshKey = 'starchef_refresh_token';
  static const _userKey = 'starchef_user';
  final SecureValueStore _storage;
  AuthSession? _initialSession;

  @override
  Future<void> save(AuthSession session) async {
    await Future.wait([
      _storage.write(_accessKey, session.accessToken),
      _storage.write(_refreshKey, session.refreshToken),
      _storage.write(_userKey, jsonEncode(session.user.toJson())),
    ]);
  }

  @override
  Future<AuthSession?> read() async {
    final inherited = _initialSession;
    _initialSession = null;
    if (inherited != null) return inherited;
    try {
      final values = await Future.wait([
        _storage.read(_accessKey),
        _storage.read(_refreshKey),
        _storage.read(_userKey),
      ]);
      if (values.any((value) => value == null)) return null;
      return AuthSession(
        accessToken: values[0]!,
        refreshToken: values[1]!,
        user: AuthUser.fromJson(jsonDecode(values[2]!) as Map<String, dynamic>),
      );
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> clear() async {
    await Future.wait([
      _storage.delete(_accessKey),
      _storage.delete(_refreshKey),
      _storage.delete(_userKey),
    ]);
  }
}
