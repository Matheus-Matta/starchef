import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../features/auth/domain/waiter_session.dart';

abstract interface class SessionStorage {
  Future<WaiterSession?> readSession();
  Future<void> saveSession(WaiterSession session);
  Future<void> clearSession();
  Future<String?> readNodeId();
  Future<void> saveNodeId(String value);
}

class SecureSessionStore implements SessionStorage {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _sessionKey = 'starchef_pdv_mobile_session';
  static const _nodeKey = 'starchef_pdv_mobile_node_id';
  final FlutterSecureStorage _storage;

  @override
  Future<WaiterSession?> readSession() async {
    try {
      final raw = await _storage.read(key: _sessionKey);
      if (raw == null || raw.isEmpty) return null;
      return WaiterSession.fromJson(
        Map<String, dynamic>.from(jsonDecode(raw) as Map),
      );
    } catch (_) {
      return null;
    }
  }

  @override
  Future<void> saveSession(WaiterSession session) =>
      _storage.write(key: _sessionKey, value: jsonEncode(session.toJson()));

  @override
  Future<void> clearSession() => _storage.delete(key: _sessionKey);

  @override
  Future<String?> readNodeId() => _storage.read(key: _nodeKey);

  @override
  Future<void> saveNodeId(String value) =>
      _storage.write(key: _nodeKey, value: value);
}
