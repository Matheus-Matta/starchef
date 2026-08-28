import 'dart:math';

/// Identificadores criados pelo terminal ANTES de qualquer chamada à API.
///
/// É o alicerce da idempotência (§7 da arquitetura offline): o registro nasce
/// com o mesmo identificador que ele terá no servidor, então um reenvio
/// causado por timeout não pode criar uma segunda venda — o backend reconhece
/// a `Idempotency-Key` e devolve a resposta original
/// (`apps/core/idempotency.py`).
abstract final class LocalId {
  static final Random _random = Random.secure();

  /// UUID v4 canônico.
  static String uuid() {
    final bytes = List<int>.generate(16, (_) => _random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // versão 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variante RFC 4122
    final hex = bytes
        .map((byte) => byte.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
        '${hex.substring(12, 16)}-${hex.substring(16, 20)}-'
        '${hex.substring(20)}';
  }

  /// Prefixo dos IDs que ainda não foram confirmados pelo servidor.
  ///
  /// Mantido igual ao histórico (`offline-`) porque telas, fila e o mapa de
  /// IDs já reconhecem esse prefixo — trocá-lo deixaria pendências antigas
  /// órfãs no primeiro update.
  static const temporaryPrefix = 'offline-';

  /// Identificador local de um recurso que ainda não existe no servidor.
  static String temporary() => '$temporaryPrefix${uuid()}';

  static bool isTemporary(String? id) =>
      id != null && id.startsWith(temporaryPrefix);
}
