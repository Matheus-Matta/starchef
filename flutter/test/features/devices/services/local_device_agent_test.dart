import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/realtime_client.dart';
import 'package:starchef_pdv/features/devices/services/local_device_agent.dart';

void main() {
  group('LocalDeviceAgent filtro de evento em tempo real', () {
    test('aceita PrintJob do próprio restaurante', () {
      final event = RealtimeEvent('model.updated', {
        'resource': 'printers.printjob',
        'restaurant_id': 'r1',
      });
      expect(LocalDeviceAgent.isPrintJobEvent(event, 'r1'), isTrue);
    });

    test('ignora PrintJob de outro restaurante da mesma conta', () {
      // O grupo do WS é por conta, não por restaurante: sem esse filtro o
      // agente reagiria a trabalhos de impressão de unidades que não são a
      // dele.
      final event = RealtimeEvent('model.updated', {
        'resource': 'printers.printjob',
        'restaurant_id': 'r2',
      });
      expect(LocalDeviceAgent.isPrintJobEvent(event, 'r1'), isFalse);
    });

    test('ignora eventos de outros modelos', () {
      final event = RealtimeEvent('model.updated', {
        'resource': 'orders.order',
        'restaurant_id': 'r1',
      });
      expect(LocalDeviceAgent.isPrintJobEvent(event, 'r1'), isFalse);
    });

    test('reconhece alterações de impressora e balança da unidade', () {
      for (final resource in ['printers.printer', 'printers.scale']) {
        final event = RealtimeEvent('model.updated', {
          'resource': resource,
          'restaurant_id': 'r1',
        });
        expect(
          LocalDeviceAgent.isDeviceConfigurationEvent(event, 'r1'),
          isTrue,
        );
      }
    });

    test('ignora configuração de equipamento de outra unidade', () {
      final event = RealtimeEvent('model.updated', {
        'resource': 'printers.printer',
        'restaurant_id': 'r2',
      });
      expect(LocalDeviceAgent.isDeviceConfigurationEvent(event, 'r1'), isFalse);
    });
  });

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
        expect(bytes.sublist(barcodeStart + barcode.length), [
          10,
          10,
          10,
          29,
          86,
          0,
        ]);
      },
    );

    test(
      'selects PC850 and encodes Brazilian accents without UTF-8 mojibake',
      () {
        final bytes = LocalDeviceAgent.rawTransportBytes(
          'Serviço · preferência',
          isEscPos: true,
        );

        expect(bytes, containsAllInOrder([0x1b, 0x74, 0x02]));
        expect(
          bytes,
          containsAllInOrder([0x53, 0x65, 0x72, 0x76, 0x69, 0x87, 0x6f]),
        );
        expect(bytes, isNot(containsAllInOrder(utf8.encode('Serviço'))));
      },
    );
  });

  group('LocalDeviceAgent QR payload (DANFE NFC-e)', () {
    test('extracts qr_data only from payload version 2', () {
      expect(
        LocalDeviceAgent.qrValueFromPayload({
          'payload_version': 2,
          'qr_data': ' https://sefaz.sp.gov.br/nfce?p=abc ',
        }),
        'https://sefaz.sp.gov.br/nfce?p=abc',
      );
      expect(
        LocalDeviceAgent.qrValueFromPayload({
          'payload_version': 1,
          'qr_data': 'https://sefaz.sp.gov.br/nfce?p=abc',
        }),
        isNull,
      );
      expect(
        LocalDeviceAgent.qrValueFromPayload({
          'payload_version': 2,
          'qr_data': '   ',
        }),
        isNull,
      );
      expect(
        LocalDeviceAgent.qrValueFromPayload({'payload_version': 2}),
        isNull,
      );
    });
  });

  group('LocalDeviceAgent ESC/POS QR Code', () {
    test(
      'encodes a GS ( k sequence: model, size, correction, store, print',
      () {
        final bytes = LocalDeviceAgent.escPosQrCodeBytes('abc')!;
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
      final bytes = LocalDeviceAgent.escPosQrCodeBytes(longUrl)!;
      final data = utf8.encode(longUrl);
      final storeLength = 3 + data.length;

      final storeCmd = bytes.indexOf(0x50); // fn='P' (store).
      // Os dois bytes anteriores ao cn/fn são pL/pH.
      expect(bytes[storeCmd - 3], storeLength & 0xff);
      expect(bytes[storeCmd - 2], (storeLength >> 8) & 0xff);
    });

    test('rejects empty or oversized payloads', () {
      expect(LocalDeviceAgent.escPosQrCodeBytes('   '), isNull);
      final tooLong = List.filled(701, 'A').join();
      expect(LocalDeviceAgent.escPosQrCodeBytes(tooLong), isNull);
    });

    test('assembles content then QR bytes for raw transports', () {
      final qr = LocalDeviceAgent.escPosQrCodeBytes('https://x.test')!;
      final bytes = LocalDeviceAgent.rawTransportBytes(
        'DANFE',
        isEscPos: true,
        qrValue: 'https://x.test',
      );
      final qrStart = _sublistIndex(bytes, qr);

      expect(bytes, containsAllInOrder(utf8.encode('DANFE')));
      expect(bytes.sublist(qrStart, qrStart + qr.length), qr);
      expect(bytes.sublist(qrStart + qr.length), [10, 10, 10, 29, 86, 0]);
    });
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

  group('LocalDeviceAgent corte e disponibilidade', () {
    test('separa a guilhotina do conteúdo para drenar antes do corte', () {
      final bytes = LocalDeviceAgent.rawTransportBytes(
        'CUPOM LONGO',
        isEscPos: true,
      );

      final parts = LocalDeviceAgent.splitCutCommand(bytes, isEscPos: true);

      expect(parts.content, isNotEmpty);
      expect(parts.content.sublist(parts.content.length - 3), [10, 10, 10]);
      expect(parts.cut, LocalDeviceAgent.escPosCutBytes);
    });

    test(
      'publica status dinâmico retornado pela checagem de hardware',
      () async {
        var connected = true;
        final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
        final agent = LocalDeviceAgent(
          api: api,
          availabilityProbe: (_) async => connected,
        );
        final printer = <String, dynamic>{
          'connection_type': 'serial',
          'endpoint': '/dev/starchef-printer',
        };

        expect(await agent.checkPrinterAvailability(printer), isTrue);
        expect(agent.printerAvailability.value.isAvailable, isTrue);

        connected = false;
        expect(await agent.checkPrinterAvailability(printer), isFalse);
        expect(
          agent.printerAvailability.value.phase,
          PrinterAvailabilityPhase.unavailable,
        );
        await api.dispose();
      },
    );

    test('impressora ausente gera aviso amigável sem exceção nativa', () async {
      final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
      final agent = LocalDeviceAgent(
        api: api,
        availabilityProbe: (_) async => false,
      );

      expect(
        () => agent.printForPrinter({
          'connection_type': 'serial',
          'endpoint': 'COM99',
        }, 'RECIBO'),
        throwsA(
          isA<PrinterCommunicationException>().having(
            (error) => error.message,
            'message',
            contains('Falha ao comunicar com a impressora'),
          ),
        ),
      );
      await api.dispose();
    });

    test('impressão IP não abre uma conexão de teste antes do envio', () async {
      final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
      var probes = 0;
      var writes = 0;
      final agent = LocalDeviceAgent(
        api: api,
        availabilityProbe: (_) async {
          probes++;
          return false;
        },
        networkWriter: (target, bytes) async {
          writes++;
          expect(target.host, '192.0.2.10');
          expect(target.port, 9100);
          expect(bytes, isNotEmpty);
        },
      );

      await agent.printForPrinter({
        'connection_type': 'network',
        'host': '192.0.2.10',
        'port': 9100,
        'driver_type': 'escpos',
      }, 'COMANDA 42');

      expect(probes, 0);
      expect(writes, 1);
      expect(agent.printerAvailability.value.isAvailable, isTrue);
      await api.dispose();
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
