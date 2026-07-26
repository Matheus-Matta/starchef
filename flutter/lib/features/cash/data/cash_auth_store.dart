import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Guarda o hash da senha de ações do caixa no armazenamento seguro do SO
/// (criptografado em repouso). Nunca guarda o texto puro.
class CashAuthStore {
  CashAuthStore({FlutterSecureStorage? storage})
    : _storage = storage ?? const FlutterSecureStorage();

  static const _hashPrefix = 'starchef_cash_action_hash_';
  static const _restaurantIndexKey = 'starchef_cash_action_restaurants';
  final FlutterSecureStorage _storage;

  String _hashKey(String restaurantId) => '$_hashPrefix$restaurantId';

  Future<void> saveHash(String restaurantId, String hash) async {
    await _storage.write(key: _hashKey(restaurantId), value: hash);
    final ids = (await _restaurantIds())..add(restaurantId);
    await _storage.write(
      key: _restaurantIndexKey,
      value: jsonEncode(ids.toList()),
    );
  }

  Future<String?> readHash(String restaurantId) =>
      _storage.read(key: _hashKey(restaurantId));

  Future<void> clear(String restaurantId) async {
    await _storage.delete(key: _hashKey(restaurantId));
    final ids = (await _restaurantIds())..remove(restaurantId);
    await _storage.write(
      key: _restaurantIndexKey,
      value: jsonEncode(ids.toList()),
    );
  }

  Future<void> clearAll() async {
    final ids = await _restaurantIds();
    for (final id in ids) {
      await _storage.delete(key: _hashKey(id));
    }
    await _storage.delete(key: _restaurantIndexKey);
  }

  Future<Set<String>> _restaurantIds() async {
    try {
      final raw = await _storage.read(key: _restaurantIndexKey);
      if (raw == null) return <String>{};
      return (jsonDecode(raw) as List).map((item) => '$item').toSet();
    } catch (_) {
      return <String>{};
    }
  }
}
