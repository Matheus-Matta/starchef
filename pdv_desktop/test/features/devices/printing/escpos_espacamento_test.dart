import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/escpos_codec.dart';

/// A comanda da Balança Rápida saiu com as linhas encavaladas e curta.
///
/// `ESC 3 n` fixa o passo em `n` UNIDADES — e a unidade é de cada impressora:
/// 1/203" na Bematech do caixa (34 = 4,2 mm), 1/360" em outras (34 = 2,4 mm,
/// menos que a altura da letra). `ESC 2` é o passo padrão de 1/6" (4,23 mm),
/// que cada impressora converte para a própria unidade.
bool _temPassoEmUnidades(List<int> bytes) {
  for (var i = 0; i < bytes.length - 1; i++) {
    if (bytes[i] == 0x1b && bytes[i + 1] == 0x33) return true;
  }
  return false;
}

void main() {
  test('o cupom não fixa o passo da linha em unidades da impressora', () {
    final bytes = EscPosCodec.rawTransportBytes(
      'COMANDA 354\nPESO: 0,366 kg\nVALOR: R\$ 25,57',
      isEscPos: true,
    );

    expect(_temPassoEmUnidades(bytes), isFalse);
    expect(bytes, containsAllInOrder([0x1b, 0x40, 0x1b, 0x32]));
  });

  test('o avanço até a guilhotina também usa o passo padrão (~30 mm)', () {
    expect(EscPosCodec.feedBeforeCutBytes, [0x1b, 0x32, 0x1b, 0x64, 7]);
  });
}
