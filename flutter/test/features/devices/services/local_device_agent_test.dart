import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/devices/services/local_device_agent.dart';

void main() {
  group('LocalDeviceAgent Code128 payload', () {
    test('extracts Code128 only from payload version 2', () {
      expect(
        LocalDeviceAgent.code128ValueFromPayload({
          'payload_version': 2,
          'barcode': {'symbology': 'code128', 'value': ' CMD-1042 '},
        }),
        'CMD-1042',
      );
      expect(
        LocalDeviceAgent.code128ValueFromPayload({
          'payload_version': 1,
          'barcode': {'symbology': 'CODE128', 'value': 'CMD-1042'},
        }),
        isNull,
      );
      expect(
        LocalDeviceAgent.code128ValueFromPayload({
          'payload_version': 2,
          'barcode': {'symbology': 'QR', 'value': 'CMD-1042'},
        }),
        isNull,
      );
      expect(
        LocalDeviceAgent.code128ValueFromPayload({
          'payload_version': 2,
          'barcode': {'symbology': 'CODE128', 'value': '   '},
        }),
        isNull,
      );
    });
  });

  group('LocalDeviceAgent ESC/POS Code128', () {
    test('encodes a GS k Code128-B command with human-readable text', () {
      final bytes = LocalDeviceAgent.escPosCode128Bytes('ABC123');

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
      final bytes = LocalDeviceAgent.escPosCode128Bytes('A{B')!;
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
      expect(LocalDeviceAgent.escPosCode128Bytes('COMANDÁ'), isNull);
      final tooLong = List.filled(254, 'A').join();
      expect(LocalDeviceAgent.escPosCode128Bytes(tooLong), isNull);
      expect(LocalDeviceAgent.escPosCode128Bytes('   '), isNull);
    });

    test(
      'assembles content, barcode, then feed and cut for raw transports',
      () {
        final barcode = LocalDeviceAgent.escPosCode128Bytes('CMD-42')!;
        final bytes = LocalDeviceAgent.rawTransportBytes(
          'TICKET',
          isEscPos: true,
          barcodeValue: 'CMD-42',
        );
        final contentLength = utf8.encode('TICKET').length;

        expect(bytes.sublist(0, contentLength), utf8.encode('TICKET'));
        expect(
          bytes.sublist(contentLength, contentLength + barcode.length),
          barcode,
        );
        expect(bytes.sublist(contentLength + barcode.length), [
          10,
          10,
          10,
          29,
          86,
          0,
        ]);
      },
    );
  });

  group('LocalDeviceAgent barcode text fallback', () {
    test('adds an explicit fallback when raw barcode is unavailable', () {
      expect(
        LocalDeviceAgent.textWithBarcodeFallback('TICKET', 'CMD-42'),
        'TICKET\n\nCOMANDA - CODE128 (TEXTO)\nCMD-42',
      );
    });

    test('does not duplicate a fallback already rendered by the backend', () {
      const content = 'TICKET\nCOMANDA - CODE128\nCMD-42';

      expect(
        LocalDeviceAgent.textWithBarcodeFallback(content, 'CMD-42'),
        content,
      );
    });

    test('keeps textual fallback on a non-ESC/POS raw transport', () {
      final bytes = LocalDeviceAgent.rawTransportBytes(
        'TICKET',
        isEscPos: false,
        barcodeValue: 'CMD-42',
      );

      expect(utf8.decode(bytes), 'TICKET\n\nCOMANDA - CODE128 (TEXTO)\nCMD-42');
    });
  });
}
