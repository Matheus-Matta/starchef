import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/realtime_client.dart';
import 'package:starchef_pdv/core/storage/local_preferences.dart';
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
        // Depois do código de barras vem a margem em branco da nota e só
        // então o avanço de ~30 mm até a lâmina (ESC 3 40 + ESC d 6) e o
        // GS V 0 — cortar antes disso parte o rodapé do cupom ao meio.
        expect(bytes.sublist(barcodeStart + barcode.length), [
          ...List<int>.filled(LocalDeviceAgent.finalBlankLines, 0x0a),
          ...LocalDeviceAgent.escPosFeedBeforeCutBytes,
          ...LocalDeviceAgent.escPosCutBytes,
        ]);
      },
    );

    test('troca acento pela letra base em vez de mandar byte alto', () {
      // A impressora não renderiza a página de código estendida: "Ç" enviado
      // como byte alto sai "?" no papel, então vale mais "Servico" legível.
      final bytes = LocalDeviceAgent.rawTransportBytes(
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
      final bytes = LocalDeviceAgent.rawTransportBytes(
        'SERVIÇO',
        isEscPos: true,
      );

      expect(bytes, containsAllInOrder(utf8.encode('SERVICO')));
      expect(bytes, isNot(contains(0x3f)));
    });

    test('toda nota termina com margem em branco antes do corte', () {
      final bytes = LocalDeviceAgent.rawTransportBytes(
        'CUPOM',
        isEscPos: true,
      );
      final tail = LocalDeviceAgent.escPosFeedBeforeCutBytes.length +
          LocalDeviceAgent.escPosCutBytes.length;
      final margin = bytes.sublist(
        bytes.length - tail - LocalDeviceAgent.finalBlankLines,
        bytes.length - tail,
      );

      expect(margin, everyElement(0x0a));
      expect(LocalDeviceAgent.finalBlankLines, greaterThanOrEqualTo(4));
    });
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
      expect(bytes.sublist(qrStart + qr.length), [
        ...List<int>.filled(LocalDeviceAgent.finalBlankLines, 0x0a),
        ...LocalDeviceAgent.escPosFeedBeforeCutBytes,
        ...LocalDeviceAgent.escPosCutBytes,
      ]);
    });
  });

  group('LocalDeviceAgent conversão de HTML para texto (último recurso)', () {
    test(
      'não gruda rótulo e valor quando a linha de tabela vem compacta',
      () {
        // POST /orders/{id}/print/ não devolve text_content — só html — e o
        // template Django escreve a linha de subtotal numa única linha de
        // código-fonte, sem espaço nenhum entre as tags.
        const html =
            '<table><tr><td>Subtotal</td><td>R\$ 237,00</td></tr></table>';
        expect(
          LocalDeviceAgent.htmlToText(html),
          'Subtotal  R\$ 237,00',
        );
      },
    );

    test(
      'produz o mesmo resultado independente da indentação do HTML de origem',
      () {
        // A mesma linha, mas quebrada em várias linhas de código-fonte (como
        // o bloco de itens do template) — antes disso produzia uma quebra de
        // linha diferente da versão compacta, um acidente de formatação.
        const html = '<table>\n  <tr>\n    <td>1 x xtudo</td>\n'
            '    <td>R\$ 49,00</td>\n  </tr>\n</table>';
        expect(
          LocalDeviceAgent.htmlToText(html),
          '1 x xtudo  R\$ 49,00',
        );
      },
    );

    test('remove CSS/JS e normaliza entidades comuns', () {
      const html =
          '<style>td{padding:2px}</style><p>Ol&aacute; &amp; adeus</p>';
      expect(
        LocalDeviceAgent.htmlToText(html),
        'Ol&aacute; & adeus',
      );
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

      expect(
        utf8.decode(bytes),
        'TICKET\n\nCOMANDA - CODE128 (TEXTO)\nCMD-42${'\n' * 6}',
      );
    });

    test('avança o papel até a guilhotina no caminho que só aceita texto', () {
      // Sem comando de corte para enviar, as linhas em branco são o que
      // empurra o fim do cupom para além da lâmina antes de o driver cortar.
      expect(
        LocalDeviceAgent.textWithBottomMargin('TICKET'),
        'TICKET${'\n' * 6}',
      );
      expect(
        LocalDeviceAgent.textWithBottomMargin('TICKET\n'),
        'TICKET\n${'\n' * 6}',
      );
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
      // O avanço fica com o conteúdo; só a guilhotina é separada, para o
      // transporte drenar o papel antes de acionar a lâmina.
      expect(
        parts.content.sublist(parts.content.length - 6),
        LocalDeviceAgent.escPosFeedBeforeCutBytes,
      );
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
          'name': 'Cozinha',
          'connection_type': 'serial',
          'endpoint': 'COM99',
        }, 'RECIBO'),
        throwsA(
          isA<PrinterCommunicationException>().having(
            (error) => error.message,
            'message',
            // O aviso precisa dizer QUAL impressora falhou: o terminal tem
            // mais de uma, e "impressora desconectada" sozinho não ajuda.
            allOf(contains('Cozinha'), contains('COM99')),
          ),
        ),
      );
      await api.dispose();
    });

    test(
      'usa a porta do cadastro, ignorando override local antigo',
      () async {
        final directory = await Directory.systemTemp.createTemp(
          'starchef-device-agent-prefs',
        );
        addTearDown(() => directory.delete(recursive: true));
        final preferences = LocalPreferences(
          file: File('${directory.path}/preferences.json'),
        );
        // Override gravado por uma versão anterior do PDV.
        await File('${directory.path}/preferences.json').writeAsString(
          '{"serial_port_overrides":{"printer:printer-1":"/dev/porta-antiga"}}',
        );
        await preferences.load();

        String? probedEndpoint;
        final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
        final agent = LocalDeviceAgent(
          api: api,
          preferences: preferences,
          availabilityProbe: (target) async {
            probedEndpoint = target.endpoint;
            return false;
          },
        );

        // Toda impressão abre a porta do cadastro. Enquanto o override
        // vencia, uma porta salva neste PC ficava desatualizada em relação ao
        // cadastro e a impressão real abria um dispositivo diferente do que o
        // teste de conexão abria — teste passando e cupom não saindo.
        await expectLater(
          agent.printForPrinter({
            'id': 'printer-1',
            'connection_type': 'serial',
            'endpoint': '/dev/ttyACM0',
          }, 'RECIBO'),
          throwsA(isA<PrinterCommunicationException>()),
        );
        expect(probedEndpoint, '/dev/ttyACM0');
        await api.dispose();
      },
    );

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
