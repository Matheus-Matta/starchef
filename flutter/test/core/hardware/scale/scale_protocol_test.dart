import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_protocol.dart';

List<int> frame(String value) => utf8.encode(value);

void main() {
  group('GenericNumericProtocol', () {
    test('extrai o peso da última linha completa', () {
      final protocol = GenericNumericProtocol();
      final samples = protocol.decode(frame('PESO 1.250 kg\r\n'));

      expect(samples, hasLength(1));
      expect(samples.single.weightKg, closeTo(1.250, 0.0001));
      expect(samples.single.stable, isNull);
    });

    test('converte gramas quando não há separador decimal', () {
      final protocol = GenericNumericProtocol();
      final samples = protocol.decode(frame('1500\r'));

      expect(samples.single.weightKg, closeTo(1.5, 0.0001));
    });

    test('não emite nada enquanto o quadro está incompleto', () {
      final protocol = GenericNumericProtocol();

      expect(protocol.decode(frame('0.7')), isEmpty);
      final samples = protocol.decode(frame('50\n'));
      expect(samples.single.weightKg, closeTo(0.750, 0.0001));
    });

    test('marca peso negativo sem inverter o valor', () {
      final protocol = GenericNumericProtocol();
      final samples = protocol.decode(frame('-0.320\n'));

      expect(samples.single.negative, isTrue);
      expect(samples.single.weightKg, closeTo(0.320, 0.0001));
    });
  });

  group('ToledoProtocol', () {
    test('decodifica quadro entre STX e ETX com casas implícitas', () {
      final protocol = ToledoProtocol();
      final samples = protocol.decode([0x02, ...frame('001250'), 0x03]);

      expect(samples.single.weightKg, closeTo(1.250, 0.0001));
      expect(samples.single.stable, isTrue);
    });

    test('reconhece a marca de instabilidade', () {
      final protocol = ToledoProtocol();
      final samples = protocol.decode([0x02, ...frame('I001250'), 0x03]);

      expect(samples.single.stable, isFalse);
    });

    test('um novo STX descarta o quadro parcial anterior', () {
      final protocol = ToledoProtocol();
      protocol.decode([0x02, ...frame('0012')]);
      final samples = protocol.decode([0x02, ...frame('000500'), 0x03]);

      expect(samples.single.weightKg, closeTo(0.500, 0.0001));
    });
  });

  group('FilizolaProtocol', () {
    test('lê gramas terminadas em CR', () {
      final protocol = FilizolaProtocol();
      final samples = protocol.decode(frame('000850\r'));

      expect(samples.single.weightKg, closeTo(0.850, 0.0001));
      expect(samples.single.stable, isNull);
    });

    test('interpreta o campo de estabilidade quando presente', () {
      final protocol = FilizolaProtocol();

      expect(protocol.decode(frame('S000850\r')).single.stable, isTrue);
      expect(protocol.decode(frame('U000850\r')).single.stable, isFalse);
    });
  });

  group('UranoProtocol', () {
    test('lê o formato com sinal, ponto decimal e unidade', () {
      final protocol = UranoProtocol();
      final samples = protocol.decode(frame('+00.500kg\r\n'));

      expect(samples.single.weightKg, closeTo(0.500, 0.0001));
      expect(samples.single.negative, isFalse);
    });

    test('converte quando a unidade transmitida é grama', () {
      final protocol = UranoProtocol();
      final samples = protocol.decode(frame('+500g\r'));

      expect(samples.single.weightKg, closeTo(0.500, 0.0001));
    });
  });

  test('forId devolve o protocolo persistido no cadastro', () {
    expect(ScaleProtocol.forId('toledo'), isA<ToledoProtocol>());
    expect(ScaleProtocol.forId('FILIZOLA'), isA<FilizolaProtocol>());
    expect(ScaleProtocol.forId(' urano '), isA<UranoProtocol>());
    expect(ScaleProtocol.forId(null), isA<GenericNumericProtocol>());
    expect(ScaleProtocol.forId('inexistente'), isA<GenericNumericProtocol>());
  });
}
