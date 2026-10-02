import 'dart:convert';
import 'dart:math';

import 'escpos_codec.dart';

/// A etiqueta da comanda, para quem não tem cartão físico.
///
/// O número bem grande no topo, centralizado, para o garçom achar de longe; o
/// QR Code e o código de barras embaixo, com o mesmo valor que o leitor do PDV
/// já reconhece (o código da comanda, ou o número quando ela não tem código).
abstract final class CommandLabelCodec {
  /// Largura útil de 58 mm em pontos (fonte A tem 12 pontos por caractere).
  /// O tamanho do número se ajusta aos dígitos para caber também nela.
  static const _pontosDaLinha = 384;

  static List<int> bytes({
    required String number,
    required String code,
    required bool isEscPos,
  }) {
    final numero = number.trim();
    final valor = code.trim().isEmpty ? numero : code.trim();
    if (!isEscPos) {
      // Driver do sistema: não há tamanho de fonte nem símbolo, só texto.
      return utf8.encode('COMANDA $numero\n\n$valor\n${'\n' * 6}');
    }
    final barras = EscPosCodec.code128Bytes(valor);
    return <int>[
      0x1b, 0x40, // ESC @: inicializa.
      0x1b, 0x61, 0x01, // ESC a 1: centraliza.
      0x1d, 0x21, tamanhoDoNumero(numero.length), // GS !: largura x altura.
      ...EscPosCodec.encodePrintable(numero),
      0x0a,
      0x1d, 0x21, 0x00, // Volta ao tamanho normal.
      ...?EscPosCodec.qrCodeBytes(valor),
      // Valor fora do Code128 (acento, por exemplo): sai em texto.
      ...barras ?? [0x0a, ...EscPosCodec.encodePrintable(valor), 0x0a],
      ...List<int>.filled(EscPosCodec.finalBlankLines, 0x0a),
      ...EscPosCodec.feedBeforeCutBytes,
      ...EscPosCodec.cutBytes,
    ];
  }

  /// O `n` do `GS !`: o mesmo multiplicador na largura e na altura, o maior
  /// (até 6x) em que os dígitos cabem na linha de 58 mm.
  static int tamanhoDoNumero(int digitos) {
    final multiplicador = (_pontosDaLinha ~/ (12 * max(digitos, 1))).clamp(
      1,
      6,
    );
    return ((multiplicador - 1) << 4) | (multiplicador - 1);
  }
}
