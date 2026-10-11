import 'dart:math';

/// Identificadores criados pelo terminal.
///
/// Nomeiam o que é local — um trabalho na fila da impressora, a reserva do
/// processo que está imprimindo — e o RECEBIMENTO: ele nasce com o UUID dado
/// aqui, para ser o mesmo na loja e na nuvem (`home_page_payment.dart`).
/// Pedido e caixa continuam recebendo o id do backend.
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
}
