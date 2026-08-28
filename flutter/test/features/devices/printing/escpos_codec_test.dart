import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/devices/printing/escpos_codec.dart';

void main() {
  group('ESC/POS Code128', () {
    test('encodes a GS k Code128-B command with human-readable text', () {
      final bytes = EscPosCodec.code128Bytes('ABC123');

      expect(bytes, isNotNull);
      expect(
        bytes,
        containsAllInOrder([
          0x1d,
          0x48,
          0x02,
          0x1d,
          0x68,
          0x50,
          0x1d,
          0x77,
          0x02,
          0x1d,
          0x6b,
          0x49,
          8,
          0x7b,
          0x42,
          0x41,
          0x42,
          0x43,
          0x31,
          0x32,
          0x33,
        ]),
      );
      expect(bytes!.sublist(bytes.length - 4), [0x0a, 0x1b, 0x61, 0x00]);
    });

    test('escapes literal braces in Code128-B data', () {
      final bytes = EscPosCodec.code128Bytes('A{B')!;
      final gsK = bytes.indexOf(0x49);

      expect(bytes.sublist(gsK + 1, gsK + 8), [
        6,
        0x7b,
        0x42,
        0x41,
        0x7b,
        0x7b,
        0x42,
      ]);
    });

    test('rejects values that cannot be represented safely', () {
      expect(EscPosCodec.code128Bytes('COMANDÁ'), isNull);
      final tooLong = List.filled(254, 'A').join();
      expect(EscPosCodec.code128Bytes(tooLong), isNull);
      expect(EscPosCodec.code128Bytes('   '), isNull);
    });

    test(
      'assembles content, barcode, then feed and cut for raw transports',
      () {
        final barcode = EscPosCodec.code128Bytes('CMD-42')!;
        final bytes = EscPosCodec.rawTransportBytes(
          'TICKET',
          isEscPos: true,
          barcodeValue: 'CMD-42',
        );
        final barcodeStart = _sublistIndex(bytes, barcode);

        expect(
          bytes,
          containsAllInOrder([0x1b, 0x40, 0x1b, 0x74, 0x02, 0x1b, 0x33, 34]),
        );
        expect(bytes, containsAllInOrder(utf8.encode('TICKET')));
        expect(
          bytes.sublist(barcodeStart, barcodeStart + barcode.length),
          barcode,
        );
        // Depois do código de barras vem a margem em branco da nota e só
        // então o avanço de ~30 mm até a lâmina (ESC 3 40 + ESC d 6) e o
        // GS V 0 — cortar antes disso parte o rodapé do cupom ao meio.
        expect(bytes.sublist(barcodeStart + barcode.length), [
          ...List<int>.filled(EscPosCodec.finalBlankLines, 0x0a),
          ...EscPosCodec.feedBeforeCutBytes,
          ...EscPosCodec.cutBytes,
        ]);
      },
    );

    test('troca acento pela letra base em vez de mandar byte alto', () {
      // A impressora não renderiza a página de código estendida: "Ç" enviado
      // como byte alto sai "?" no papel, então vale mais "Servico" legível.
      final bytes = EscPosCodec.rawTransportBytes(
        'Serviço · preferência',
        isEscPos: true,
      );

      expect(bytes, containsAllInOrder(utf8.encode('Servico')));
      expect(bytes, containsAllInOrder(utf8.encode('preferencia')));
      // Nada de byte alto nem de "?" no lugar dos acentos.
      expect(bytes.sublist(0, bytes.length - 3), isNot(contains(0x3f)));
      expect(bytes, isNot(containsAllInOrder(utf8.encode('Serviço'))));
    });

    test('acento combinante (NFD) não vira "?" no papel', () {
      // "Ç" pode chegar decomposto: "C" + cedilha combinante (U+0327).
      final bytes = EscPosCodec.rawTransportBytes(
        'SERVIÇO',
        isEscPos: true,
      );

      expect(bytes, containsAllInOrder(utf8.encode('SERVICO')));
      expect(bytes, isNot(contains(0x3f)));
    });

    test('toda nota termina com margem em branco antes do corte', () {
      final bytes = EscPosCodec.rawTransportBytes(
        'CUPOM',
        isEscPos: true,
      );
      final tail = EscPosCodec.feedBeforeCutBytes.length +
          EscPosCodec.cutBytes.length;
      final margin = bytes.sublist(
        bytes.length - tail - EscPosCodec.finalBlankLines,
        bytes.length - tail,
      );

      expect(margin, everyElement(0x0a));
      expect(EscPosCodec.finalBlankLines, greaterThanOrEqualTo(4));
    });
  });

  group('ESC/POS QR Code', () {
    test(
      'encodes a GS ( k sequence: model, size, correction, store, print',
      () {
        final bytes = EscPosCodec.qrCodeBytes('abc')!;
        final data = utf8.encode('abc');

        expect(
          bytes,
          containsAllInOrder([
            // Select model 2.
            0x1d, 0x28, 0x6b, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00,
            // Module size 6.
            0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x43, 0x06,
            // Error correction level M.
            0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x45, 0x31,
            // Store data (pL/pH = 3 + len(data) = 6, little-endian).
            0x1d, 0x28, 0x6b, 3 + data.length, 0x00, 0x31, 0x50, 0x30,
            ...data,
            // Print symbol.
            0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x51, 0x30,
          ]),
        );
        expect(bytes.first, 0x0a);
        expect(bytes.sublist(1, 4), [0x1b, 0x61, 0x01]); // center before.
        expect(bytes.sublist(bytes.length - 4), [
          0x0a,
          0x1b,
          0x61,
          0x00,
        ]); // restore after.
      },
    );

    test('computes a two-byte little-endian length for larger payloads', () {
      final longUrl = 'https://sefaz.sp.gov.br/nfce?p=${'0' * 300}';
      final bytes = EscPosCodec.qrCodeBytes(longUrl)!;
      final data = utf8.encode(longUrl);
      final storeLength = 3 + data.length;

      final storeCmd = bytes.indexOf(0x50); // fn='P' (store).
      // Os dois bytes anteriores ao cn/fn são pL/pH.
      expect(bytes[storeCmd - 3], storeLength & 0xff);
      expect(bytes[storeCmd - 2], (storeLength >> 8) & 0xff);
    });

    test('rejects empty or oversized payloads', () {
      expect(EscPosCodec.qrCodeBytes('   '), isNull);
      final tooLong = List.filled(701, 'A').join();
      expect(EscPosCodec.qrCodeBytes(tooLong), isNull);
    });

    test('assembles content then QR bytes for raw transports', () {
      final qr = EscPosCodec.qrCodeBytes('https://x.test')!;
      final bytes = EscPosCodec.rawTransportBytes(
        'DANFE',
        isEscPos: true,
        qrValue: 'https://x.test',
      );
      final qrStart = _sublistIndex(bytes, qr);

      expect(bytes, containsAllInOrder(utf8.encode('DANFE')));
      expect(bytes.sublist(qrStart, qrStart + qr.length), qr);
      expect(bytes.sublist(qrStart + qr.length), [
        ...List<int>.filled(EscPosCodec.finalBlankLines, 0x0a),
        ...EscPosCodec.feedBeforeCutBytes,
        ...EscPosCodec.cutBytes,
      ]);
    });
  });

  group('barcode text fallback', () {
    test('adds an explicit fallback when raw barcode is unavailable', () {
      expect(
        EscPosCodec.textWithBarcodeFallback('TICKET', 'CMD-42'),
        'TICKET\n\nCOMANDA - CODE128 (TEXTO)\nCMD-42',
      );
    });

    test('does not duplicate a fallback already rendered by the backend', () {
      const content = 'TICKET\nCOMANDA - CODE128\nCMD-42';

      expect(
        EscPosCodec.textWithBarcodeFallback(content, 'CMD-42'),
        content,
      );
    });

    test('keeps textual fallback on a non-ESC/POS raw transport', () {
      final bytes = EscPosCodec.rawTransportBytes(
        'TICKET',
        isEscPos: false,
        barcodeValue: 'CMD-42',
      );

      expect(
        utf8.decode(bytes),
        'TICKET\n\nCOMANDA - CODE128 (TEXTO)\nCMD-42${'\n' * 6}',
      );
    });

    test('avança o papel até a guilhotina no caminho que só aceita texto', () {
      // Sem comando de corte para enviar, as linhas em branco são o que
      // empurra o fim do cupom para além da lâmina antes de o driver cortar.
      expect(
        EscPosCodec.textWithBottomMargin('TICKET'),
        'TICKET${'\n' * 6}',
      );
      expect(
        EscPosCodec.textWithBottomMargin('TICKET\n'),
        'TICKET\n${'\n' * 6}',
      );
    });
  });

  group('corte', () {
    test('separa a guilhotina do conteúdo para drenar antes do corte', () {
      final bytes = EscPosCodec.rawTransportBytes(
        'CUPOM LONGO',
        isEscPos: true,
      );

      final parts = EscPosCodec.splitCutCommand(bytes, isEscPos: true);

      expect(parts.content, isNotEmpty);
      // O avanço fica com o conteúdo; só a guilhotina é separada, para o
      // transporte drenar o papel antes de acionar a lâmina.
      expect(
        parts.content.sublist(parts.content.length - 6),
        EscPosCodec.feedBeforeCutBytes,
      );
      expect(parts.cut, EscPosCodec.cutBytes);
    });
  });
}

int _sublistIndex(List<int> source, List<int> pattern) {
  for (var index = 0; index <= source.length - pattern.length; index++) {
    if (source.sublist(index, index + pattern.length).join(',') ==
        pattern.join(',')) {
      return index;
    }
  }
  return -1;
}
