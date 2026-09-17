import 'dart:convert';

/// Conversão de um cupom em texto para os bytes que a impressora recebe.
///
/// É o único lugar que sabe montar byte de impressora: corte, avanço, código
/// de barras, QR Code, acentuação e tipografia. Antes isso vivia misturado ao
/// agente que também falava com o servidor, sincronizava modelos e girava a
/// fila — mexer no corte exigia entender o WebSocket.
///
/// Não conhece transporte nem cadastro: recebe texto, devolve bytes.
abstract final class EscPosCodec {
  /// `GS V 0` — corte total. O byte final aceita tanto `0x00` quanto `'0'`
  /// (0x30) no padrão ESC/POS; mantemos `0x00`, que é o que as térmicas
  /// vendidas aqui já vinham aceitando.
  static const List<int> cutBytes = [0x1d, 0x56, 0x00];

  /// Avanço de papel obrigatório entre a última linha e a guilhotina.
  ///
  /// A lâmina fica 2 a 3 cm acima da cabeça térmica: acionar o corte logo
  /// depois do texto corta o rodapé ao meio — ou empurra o final do cupom
  /// para o começo do próximo. `ESC 3 40` fixa o passo em 40 pontos (5 mm a
  /// 203 dpi) e `ESC d 6` avança seis linhas, ~30 mm, folga suficiente para
  /// o fim do cupom ultrapassar a lâmina em qualquer térmica de 80 mm.
  ///
  /// Um único `ESC d` em vez de vários `LF` soltos é deliberado: foi a
  /// sequência de LFs repetidos que causou o corte duplo na MP-4200 HS.
  static const List<int> feedBeforeCutBytes = [
    0x1b, 0x33, 40, // ESC 3 40: passo de 40 pontos só para o avanço final.
    0x1b, 0x64, 6, // ESC d 6: seis avanços de linha (~30 mm).
  ];

  /// Linhas em branco impressas ao final de toda nota, como respiro entre o
  /// último dado e o corte. Não substitui o avanço mecânico da guilhotina.
  static const int finalBlankLines = 5;

  /// Produces an ESC/POS `GS k` Code128 command using code set B.
  ///
  /// Code set B is deliberately limited to printable ASCII. Values outside
  /// that range stay available through the explicit text fallback instead of
  /// sending a malformed barcode to the printer.
  static List<int>? code128Bytes(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) return null;

    final data = <int>[0x7b, 0x42]; // `{B`: select Code128 set B.
    for (final rune in normalized.runes) {
      if (rune < 0x20 || rune > 0x7e) return null;
      if (rune == 0x7b) {
        data.add(0x7b); // A literal `{` is escaped as `{{` in ESC/POS.
      }
      data.add(rune);
    }
    if (data.length > 255) return null;

    return <int>[
      0x0a,
      0x0a,
      0x1b,
      0x61,
      0x01, // ESC a: center.
      0x1d,
      0x48,
      0x02, // GS H: human-readable value below the bars.
      0x1d,
      0x68,
      0x50, // GS h: 80-dot height.
      0x1d,
      0x77,
      0x02, // GS w: module width 2.
      0x1d,
      0x6b,
      0x49,
      data.length,
      ...data,
      0x0a,
      0x1b,
      0x61,
      0x00, // Restore left alignment for following output.
    ];
  }

  /// Produces an ESC/POS `GS ( k` 2D symbol (QR Code) command sequence.
  ///
  /// Standard Epson ESC/POS "Function 165" sequence, supported by the large
  /// majority of ESC/POS-compatible thermal printers (Epson TM series and
  /// most clones — Bematech, Elgin, Daruma etc. implement the same command
  /// set). Model 2, module size 6 dots, error correction level M (recovers
  /// up to ~15% damage) — a reasonable default for a NFC-e DANFE, where the
  /// QR needs to stay scannable on thermal paper that can fade/crease.
  static List<int>? qrCodeBytes(String data) {
    final bytes = utf8.encode(data.trim());
    if (bytes.isEmpty || bytes.length > 700) return null;

    final storeLength = 3 + bytes.length; // cn + fn + m + data
    final pL = storeLength & 0xff;
    final pH = (storeLength >> 8) & 0xff;

    return <int>[
      0x0a,
      0x1b, 0x61, 0x01, // ESC a: center.
      // Select the model: cn=49('1') fn=65('A') n1=model2(50) n2=0.
      0x1d, 0x28, 0x6b, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00,
      // Set module size: cn=49 fn=67('C') n=6.
      0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x43, 0x06,
      // Set error correction level: cn=49 fn=69('E') n=49 (level M).
      0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x45, 0x31,
      // Store the data: cn=49 fn=80('P') m=48('0') + payload.
      0x1d, 0x28, 0x6b, pL, pH, 0x31, 0x50, 0x30,
      ...bytes,
      // Print the symbol: cn=49 fn=81('Q') m=48('0').
      0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x51, 0x30,
      0x0a,
      0x1b, 0x61, 0x00, // Restore left alignment.
    ];
  }

  /// Repete o valor do código de barras em texto quando o equipamento não
  /// imprime o símbolo — sem isso a comanda sairia sem referência nenhuma.
  static String textWithBarcodeFallback(String content, String? value) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) return content;
    final alreadyExplicit =
        content.toUpperCase().contains('CODE128') &&
        content.contains(normalized);
    if (alreadyExplicit) return content;

    final separator = content.endsWith('\n') ? '\n' : '\n\n';
    return '$content${separator}COMANDA - CODE128 (TEXTO)\n$normalized';
  }

  /// Margem inferior do caminho que só aceita texto (driver gráfico do
  /// sistema e transportes não-ESC/POS).
  ///
  /// Sem comando de corte para enviar, o papel precisa subir sozinho antes de
  /// o driver acionar a guilhotina no fim do documento — mesma folga de ~2 a
  /// 3 cm que [feedBeforeCutBytes] garante no caminho RAW, aqui obtida com
  /// seis linhas em branco.
  static String textWithBottomMargin(String content) => '$content${'\n' * 6}';

  /// Builds the exact byte stream sent through raw network or serial links.
  ///
  /// [qrValue] is exclusive to fiscal DANFE jobs (NFC-e QR Code) — a job never
  /// carries both a barcode and a QR value, but both parameters are accepted
  /// independently to keep this a plain byte-stream builder, not a job-type
  /// switch.
  static List<int> rawTransportBytes(
    String content, {
    required bool isEscPos,
    String? barcodeValue,
    String? qrValue,
  }) {
    final barcodeBytes = isEscPos && barcodeValue != null
        ? code128Bytes(barcodeValue)
        : null;
    final qrBytes = isEscPos && qrValue != null ? qrCodeBytes(qrValue) : null;
    final printableContent = barcodeBytes == null
        ? textWithBarcodeFallback(content, barcodeValue)
        : content;
    final transportContent = isEscPos
        ? printableContent
        : textWithBottomMargin(printableContent);
    final contentBytes = isEscPos
        ? _readableReceiptBytes(transportContent)
        : utf8.encode(transportContent);
    return <int>[
      ...contentBytes,
      ...?barcodeBytes,
      ...?qrBytes,
      // Margem em branco no fim de toda nota, depois do código de barras e
      // antes do avanço mecânico. É espaço de CONTEÚDO: a folga da guilhotina
      // continua sendo [feedBeforeCutBytes], que não muda.
      if (isEscPos) ...List<int>.filled(finalBlankLines, 0x0a),
      // Ordem obrigatória para qualquer cupom: conteúdo, avanço até a lâmina
      // e só então a guilhotina — ver [feedBeforeCutBytes].
      if (isEscPos) ...[...feedBeforeCutBytes, ...cutBytes],
    ];
  }

  /// Separa o comando de corte para que o transporte possa drenar o conteúdo
  /// antes de enviá-lo. O retorno mantém os avanços de papel junto ao corpo.
  static ({List<int> content, List<int> cut}) splitCutCommand(
    List<int> bytes, {
    required bool isEscPos,
  }) {
    if (!isEscPos || bytes.length < cutBytes.length) {
      return (content: List<int>.from(bytes), cut: const <int>[]);
    }
    final cutStart = bytes.length - cutBytes.length;
    final hasCut =
        List<int>.generate(
          cutBytes.length,
          (index) => bytes[cutStart + index],
        ).join(',') ==
        cutBytes.join(',');
    if (!hasCut) {
      return (content: List<int>.from(bytes), cut: const <int>[]);
    }
    return (content: bytes.sublist(0, cutStart), cut: bytes.sublist(cutStart));
  }

  /// Applies conservative ESC/POS typography that remains readable on both
  /// 58 mm and 80 mm rolls: larger line spacing, emphasized first line and
  /// double-height totals. Width is kept normal so item values are not cut.
  static List<int> _readableReceiptBytes(String content) {
    final result = <int>[
      0x1b, 0x40, // Initialize.
      0x1b, 0x74, 0x02, // ESC t 2: pagina PC850 (padrao brasileiro).
      0x1b, 0x33, 34, // Comfortable line spacing.
      0x1d, 0x4c, 8, 0, // Small left margin.
    ];
    var firstTextLine = true;
    for (final line in content.split('\n')) {
      final normalized = line.trim().toUpperCase();
      final prominent = firstTextLine || normalized.startsWith('TOTAL');
      result.addAll([0x1b, 0x21, prominent ? 0x10 : 0x00]);
      result.addAll(encodePrintable(line));
      result.add(0x0a);
      if (normalized.isNotEmpty) firstTextLine = false;
    }
    result.addAll([0x1b, 0x21, 0x00]);
    return result;
  }

  /// Reduz o texto a ASCII imprimível antes de enviar à impressora.
  ///
  /// As térmicas em uso não renderizam a página de código estendida: um "Ç"
  /// enviado como byte alto sai como "?" no papel, e a palavra fica pior do
  /// que sem o acento. Trocar pela letra base ("Ç" -> "C", "ã" -> "a") sai
  /// legível em qualquer equipamento, que é o que importa num cupom.
  static List<int> encodePrintable(String value) {
    const equivalents = <int, String>{
      // Latim acentuado -> letra base.
      0x00c0: 'A', 0x00c1: 'A', 0x00c2: 'A', 0x00c3: 'A', 0x00c4: 'A',
      0x00c5: 'A', 0x00c7: 'C',
      0x00c8: 'E', 0x00c9: 'E', 0x00ca: 'E', 0x00cb: 'E',
      0x00cc: 'I', 0x00cd: 'I', 0x00ce: 'I', 0x00cf: 'I',
      0x00d1: 'N',
      0x00d2: 'O', 0x00d3: 'O', 0x00d4: 'O', 0x00d5: 'O', 0x00d6: 'O',
      0x00d9: 'U', 0x00da: 'U', 0x00db: 'U', 0x00dc: 'U', 0x00dd: 'Y',
      0x00e0: 'a', 0x00e1: 'a', 0x00e2: 'a', 0x00e3: 'a', 0x00e4: 'a',
      0x00e5: 'a', 0x00e7: 'c',
      0x00e8: 'e', 0x00e9: 'e', 0x00ea: 'e', 0x00eb: 'e',
      0x00ec: 'i', 0x00ed: 'i', 0x00ee: 'i', 0x00ef: 'i',
      0x00f1: 'n',
      0x00f2: 'o', 0x00f3: 'o', 0x00f4: 'o', 0x00f5: 'o', 0x00f6: 'o',
      0x00f9: 'u', 0x00fa: 'u', 0x00fb: 'u', 0x00fc: 'u',
      0x00fd: 'y', 0x00ff: 'y',
      0x00c6: 'AE', 0x00e6: 'ae', 0x00df: 'ss',
      0x00aa: 'a', 0x00ba: 'o',
      // Pontuação tipográfica que às vezes chega do template.
      0x00a0: ' ', 0x00b7: '-', 0x00d7: 'x',
      0x2013: '-', 0x2014: '-',
      0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"',
      0x2026: '...', 0x20ac: 'EUR',
    };
    final result = <int>[];
    for (final rune in value.runes) {
      if (rune <= 0x7f) {
        result.add(rune);
        continue;
      }
      // Texto decomposto (NFD) chega como letra + acento combinante. A letra
      // já foi escrita acima; o acento sozinho viraria "?" no papel.
      if (rune >= 0x0300 && rune <= 0x036f) continue;
      final equivalent = equivalents[rune];
      if (equivalent != null) {
        result.addAll(equivalent.codeUnits);
        continue;
      }
      result.add(0x3f);
    }
    return result;
  }
}
