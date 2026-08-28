import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../../../core/network/api_client.dart';
import '../../../core/security/cash_password.dart';
import '../../auth/domain/auth_session.dart';
import 'cash_auth_store.dart';

/// Sincroniza (online) o hash da senha de ações do caixa do restaurante do
/// usuário e o guarda com segurança para VERIFICAÇÃO OFFLINE quando não houver
/// rede — liberando ações do caixa que exigem autorização.
class CashAuthRepository {
  CashAuthRepository({required this.apiClient, CashAuthStore? store})
    : store = store ?? CashAuthStore();

  final ApiClient apiClient;
  final CashAuthStore store;
  // A memória guarda somente o hash PBKDF2, nunca a senha em texto puro. O
  // mesmo hash também fica no cofre criptografado do sistema para uso offline.
  final Map<String, String> _memoryHashes = {};

  /// Baixa o hash do backend e persiste localmente. Silencioso em falha
  /// (offline/sem permissão): mantém o hash já guardado.
  Future<bool> trySync(AuthSession session, {String? restaurantId}) async {
    restaurantId ??= session.user.restaurantId;
    if (restaurantId == null || restaurantId.isEmpty) return false;
    try {
      final json = await apiClient.get(
        '/restaurants/$restaurantId/cash-auth/',
        accessToken: session.accessToken,
      );
      final algorithm = '${json['algorithm'] ?? ''}';
      final hash = json['password_hash'] as String?;
      if (algorithm == 'pbkdf2_sha256' && hash != null && hash.isNotEmpty) {
        _memoryHashes[restaurantId] = hash;
        await store.saveHash(restaurantId, hash);
      } else {
        _memoryHashes.remove(restaurantId);
        await store.clear(restaurantId); // restaurante sem senha definida
      }
      return true;
    } catch (_) {
      // Offline ou sem permissão: preserva o hash local (se existir).
      return false;
    }
  }

  /// Verifica a senha OFFLINE contra o hash guardado.
  /// Retorna false se não houver senha definida/guardada.
  Future<bool> verify(String password, {required String restaurantId}) async {
    final hash =
        _memoryHashes[restaurantId] ?? await store.readHash(restaurantId);
    if (hash == null || hash.isEmpty) return false;
    _memoryHashes[restaurantId] = hash;
    return CashPassword.verify(password, hash);
  }

  /// Prova de que este terminal conhece a senha de ações do caixa.
  ///
  /// HMAC-SHA256 do hash guardado sobre `{cash_register_id}:{nonce}`. É o que
  /// permite autorizar uma divergência **sem rede** e ainda assim o servidor
  /// conferir depois, sem que a senha em texto seja gravada na fila local nem
  /// trafegue no reenvio. O backend recompõe o mesmo valor a partir do hash
  /// que ele guarda (ver `_cash_password_proof`).
  ///
  /// `null` quando não há senha sincronizada — nesse caso a autorização
  /// continua exigindo um gerente e, portanto, servidor.
  Future<String?> passwordProof({
    required String restaurantId,
    required String cashRegisterId,
    required String nonce,
  }) async {
    final hash =
        _memoryHashes[restaurantId] ?? await store.readHash(restaurantId);
    if (hash == null || hash.isEmpty) return null;
    _memoryHashes[restaurantId] = hash;
    return Hmac(
      sha256,
      utf8.encode(hash),
    ).convert(utf8.encode('$cashRegisterId:$nonce')).toString();
  }

  /// Há uma senha de caixa guardada para uso offline?
  Future<bool> hasStoredPassword(String restaurantId) async {
    final hash =
        _memoryHashes[restaurantId] ?? await store.readHash(restaurantId);
    if (hash != null && hash.isNotEmpty) _memoryHashes[restaurantId] = hash;
    return hash != null && hash.isNotEmpty;
  }

  Future<void> clear() async {
    _memoryHashes.clear();
    await store.clearAll();
  }
}
