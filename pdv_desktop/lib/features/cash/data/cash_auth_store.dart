import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../core/storage/durable_secure_store.dart';

/// Guarda somente o hash da senha de ações do caixa.
///
/// O cofre do SO é a fonte nativa; no Linux existe também a cópia durável
/// protegida pelas permissões do usuário para sobreviver sem Secret Service.
/// A senha em texto puro nunca é armazenada.
class CashAuthStore {
  CashAuthStore({FlutterSecureStorage? storage, SecureValueStore? valueStore})
    : _storage =
          valueStore ??
          DurableSecureStore(
            primary: FlutterSecureValueStore(
              storage ?? const FlutterSecureStorage(),
            ),
          );

  static const _hashPrefix = 'starchef_cash_action_hash_';
  static const _restaurantIndexKey = 'starchef_cash_action_restaurants';
  final SecureValueStore _storage;

  String _hashKey(String restaurantId) => '$_hashPrefix$restaurantId';

  Future<void> saveHash(String restaurantId, String hash) async {
    await _storage.write(_hashKey(restaurantId), hash);
    final ids = (await _restaurantIds())..add(restaurantId);
    await _storage.write(_restaurantIndexKey, jsonEncode(ids.toList()));
  }

  Future<String?> readHash(String restaurantId) =>
      _storage.read(_hashKey(restaurantId));

  Future<void> clear(String restaurantId) async {
    await _storage.delete(_hashKey(restaurantId));
    final ids = (await _restaurantIds())..remove(restaurantId);
    await _storage.write(_restaurantIndexKey, jsonEncode(ids.toList()));
  }

  Future<void> clearAll() async {
    final ids = await _restaurantIds();
    for (final id in ids) {
      await _storage.delete(_hashKey(id));
    }
    await _storage.delete(_restaurantIndexKey);
  }

  Future<Set<String>> _restaurantIds() async {
    try {
      final raw = await _storage.read(_restaurantIndexKey);
      if (raw == null) return <String>{};
      return (jsonDecode(raw) as List).map((item) => '$item').toSet();
    } catch (_) {
      return <String>{};
    }
  }
}
