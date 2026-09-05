import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../features/auth/domain/waiter_session.dart';
import '../relay/principal_client.dart';

/// Guarda a sessão do garçom e o pareamento do aparelho.
///
/// São coisas com tempos de vida diferentes, e por isso ficam em chaves
/// separadas: a **sessão** é de quem está usando agora (some no logout); o
/// **pareamento** é do aparelho (o celular continua sendo daquela loja mesmo
/// quando troca o garçom no fim do turno).
abstract interface class SessionStorage {
  Future<WaiterSession?> readSession();
  Future<void> saveSession(WaiterSession session);
  Future<void> clearSession();

  Future<PrincipalConfig?> readPrincipal();
  Future<void> savePrincipal(PrincipalConfig config);
  Future<void> clearPrincipal();

  /// Identidade deste aparelho no relay. Sobrevive a logout e a novo
  /// pareamento: é ela que o principal usa para reconhecer os recibos já
  /// entregues, então trocá-la faria uma operação repetida virar pedido
  /// duplicado.
  Future<String?> readNodeId();
  Future<void> saveNodeId(String value);
}

class SecureSessionStore implements SessionStorage {
  SecureSessionStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _sessionKey = 'starchef_garcom_session';
  static const _principalKey = 'starchef_garcom_principal';
  static const _nodeKey = 'starchef_garcom_node_id';

  final FlutterSecureStorage _storage;

  @override
  Future<WaiterSession?> readSession() =>
      _read(_sessionKey, WaiterSession.fromJson);

  @override
  Future<void> saveSession(WaiterSession session) =>
      _storage.write(key: _sessionKey, value: jsonEncode(session.toJson()));

  @override
  Future<void> clearSession() => _storage.delete(key: _sessionKey);

  @override
  Future<PrincipalConfig?> readPrincipal() =>
      _read(_principalKey, PrincipalConfig.fromJson);

  @override
  Future<void> savePrincipal(PrincipalConfig config) =>
      _storage.write(key: _principalKey, value: jsonEncode(config.toJson()));

  @override
  Future<void> clearPrincipal() => _storage.delete(key: _principalKey);

  @override
  Future<String?> readNodeId() => _storage.read(key: _nodeKey);

  @override
  Future<void> saveNodeId(String value) =>
      _storage.write(key: _nodeKey, value: value);

  Future<T?> _read<T>(
    String key,
    T Function(Map<String, dynamic>) parse,
  ) async {
    try {
      final raw = await _storage.read(key: key);
      if (raw == null || raw.isEmpty) return null;
      return parse(Map<String, dynamic>.from(jsonDecode(raw) as Map));
    } catch (_) {
      // Cofre indisponível ou conteúdo de uma versão antiga: melhor pedir de
      // novo do que abrir o app em um estado impossível.
      return null;
    }
  }
}
