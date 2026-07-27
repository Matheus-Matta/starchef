import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../features/auth/domain/auth_session.dart';

abstract interface class SessionStore {
  Future<void> save(AuthSession session);
  Future<AuthSession?> read();
  Future<void> clear();
}

class SecureSessionStore implements SessionStore {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _accessKey = 'starchef_access_token';
  static const _refreshKey = 'starchef_refresh_token';
  static const _userKey = 'starchef_user';
  final FlutterSecureStorage _storage;

  @override
  Future<void> save(AuthSession session) async {
    await Future.wait([
      _storage.write(key: _accessKey, value: session.accessToken),
      _storage.write(key: _refreshKey, value: session.refreshToken),
      _storage.write(key: _userKey, value: jsonEncode(session.user.toJson())),
    ]);
  }

  @override
  Future<AuthSession?> read() async {
    final values = await Future.wait([
      _storage.read(key: _accessKey),
      _storage.read(key: _refreshKey),
      _storage.read(key: _userKey),
    ]);
    if (values.any((value) => value == null)) return null;
    return AuthSession(
      accessToken: values[0]!,
      refreshToken: values[1]!,
      user: AuthUser.fromJson(jsonDecode(values[2]!) as Map<String, dynamic>),
    );
  }

  @override
  Future<void> clear() async {
    await Future.wait([
      _storage.delete(key: _accessKey),
      _storage.delete(key: _refreshKey),
      _storage.delete(key: _userKey),
    ]);
  }
}
