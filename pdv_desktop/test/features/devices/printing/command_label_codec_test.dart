import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/command_label_codec.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/escpos_codec.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/print_document.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/printer.dart';

/// A etiqueta da comanda: número grande no topo, QR e código de barras.
void main() {
  bool contem(List<int> tudo, List<int> trecho) {
    for (var i = 0; i + trecho.length <= tudo.length; i++) {
      var igual = true;
      for (var j = 0; j < trecho.length; j++) {
        if (tudo[i + j] != trecho[j]) {
          igual = false;
          break;
        }
      }
      if (igual) return true;
    }
    return false;
  }

  int indice(List<int> tudo, List<int> trecho) {
    for (var i = 0; i + trecho.length <= tudo.length; i++) {
      if (contem(tudo.sublist(i, i + trecho.length), trecho)) return i;
    }
    return -1;
  }

  test(
    'número grande e centralizado no topo, depois QR e código de barras',
    () {
      final bytes = CommandLabelCodec.bytes(
        number: '12',
        code: '0012',
        isEscPos: true,
      );

      final numero = indice(bytes, [0x1d, 0x21, 0x55, ...ascii.encode('12')]);
      final qr = indice(bytes, [...ascii.encode('0012'), 0x1d, 0x28, 0x6b]);
      final barras = indice(bytes, [0x7b, 0x42, ...ascii.encode('0012')]);
      expect(contem(bytes, [0x1b, 0x61, 0x01]), isTrue, reason: 'centralizado');
      expect(numero, greaterThanOrEqualTo(0), reason: 'número em 6x');
      expect(qr, greaterThan(numero), reason: 'QR depois do número');
      expect(barras, greaterThan(qr), reason: 'barras depois do QR');
      expect(contem(bytes, EscPosCodec.cutBytes), isTrue);
    },
  );

  test('o tamanho do número cabe na linha de 58 mm', () {
    expect(CommandLabelCodec.tamanhoDoNumero(1), 0x55);
    expect(CommandLabelCodec.tamanhoDoNumero(4), 0x55); // 4 x 72 pontos
    expect(CommandLabelCodec.tamanhoDoNumero(6), 0x44); // 6 x 60 pontos
    expect(CommandLabelCodec.tamanhoDoNumero(40), 0x00);
  });

  test('comanda sem código usa o número no QR e nas barras', () {
    final bytes = CommandLabelCodec.bytes(
      number: '7',
      code: ' ',
      isEscPos: true,
    );

    expect(contem(bytes, [0x7b, 0x42, ...ascii.encode('7')]), isTrue);
  });

  test('código com acento sai em texto, sem mandar Code128 inválido', () {
    final bytes = CommandLabelCodec.bytes(
      number: '3',
      code: 'MESAÇ',
      isEscPos: true,
    );

    expect(contem(bytes, [0x1d, 0x6b]), isFalse);
    expect(contem(bytes, ascii.encode('MESAC')), isTrue);
  });

  test('impressora no driver do sistema recebe texto simples', () {
    final texto = utf8.decode(
      CommandLabelCodec.bytes(number: '15', code: '0015', isEscPos: false),
    );

    expect(texto, startsWith('COMANDA 15'));
    expect(texto, contains('0015'));
  });

  test('o tipo é reconhecido e o lote não vai para a fila', () {
    final documento = PrintDocument.fromRemoteJob({
      'job_type': 'command_label',
      'payload': {
        'payload_version': 2,
        'text_content': '12',
        'barcode': {'symbology': 'CODE128', 'value': '0012'},
      },
    });
    final impressora = Printer.forDocument({
      'id': 'p1',
      'name': 'Etiquetas',
      'connection_type': 'network',
      'host': '10.0.0.9',
      'port': 9100,
      'driver_type': 'escpos',
    }, documento);

    expect(documento.type, PrintJobType.commandLabel);
    expect(impressora, isA<CommandLabelPrinter>());
    expect(impressora.queueable, isFalse);
  });
}
