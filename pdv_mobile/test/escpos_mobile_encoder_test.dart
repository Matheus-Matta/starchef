import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/features/printing/services/escpos_mobile_encoder.dart';

void main() {
  test('gera inicialização, texto e corte ESC/POS', () {
    final bytes = const EscPosMobileEncoder().encode(text: 'Café com pão');

    expect(bytes.take(2), [0x1b, 0x40]);
    expect(bytes.sublist(bytes.length - 3), [0x1d, 0x56, 0x00]);
    expect(bytes, contains(130)); // é em CP850
    expect(bytes, contains(198)); // ã em CP850
  });

  test('inclui Code 128 quando o backend envia código de barras', () {
    final bytes = const EscPosMobileEncoder().encode(
      text: 'Comanda',
      barcode: '12345',
    );

    expect(bytes, containsAllInOrder([0x1d, 0x6b, 73, 7, 0x7b, 0x42]));
  });

  test('driver de texto não recebe comandos ESC/POS', () {
    final bytes = const EscPosMobileEncoder().encode(
      text: 'Comanda',
      barcode: '12345',
      escPos: false,
    );

    expect(bytes.take(2), isNot([0x1b, 0x40]));
    expect(String.fromCharCodes(bytes), contains('CODE128 (TEXTO)'));
  });
}
