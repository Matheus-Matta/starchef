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

    test('lê o quadro contínuo, só dígitos e sem unidade', () {
      // É o que a linha UDC transmite de fato: a resolução do visor, sem
      // separador nem sufixo. Lido como número puro, `002845` virava 2845 kg
      // e a estabilidade nunca fechava — a estação ficava sem peso.
      final protocol = UranoProtocol();
      final samples = protocol.decode([0x02, ...frame('002845'), 0x03]);

      expect(samples.single.weightKg, closeTo(2.845, 0.0001));
    });

    test('lê o quadro do modo de impressão entre sequências ESC', () {
      final protocol = UranoProtocol();
      final samples = protocol.decode([0x1b, ...frame('PESO:    284 g'), 0x0d]);

      expect(samples.single.weightKg, closeTo(0.284, 0.0001));
    });

    test('valor acima de 1000 é grama, não tonelada', () {
      // Abaixo de 100 g a Urano troca a escala do quadro e o mesmo campo chega
      // mil vezes maior, sem unidade nem separador que denunciem a troca.
      final protocol = UranoProtocol();

      expect(
        protocol.decode(frame('84000.0\r')).single.weightKg,
        closeTo(84.0, 0.0001),
      );
      expect(
        protocol.decode(frame('1250.5\r')).single.weightKg,
        closeTo(1.2505, 0.0001),
      );
      // Um peso plausível continua intocado: 900 kg está abaixo do limite e
      // 0,5 kg nem chega perto dele.
      expect(
        protocol.decode(frame('+00.500kg\r')).single.weightKg,
        closeTo(0.500, 0.0001),
      );
    });

    test('pede o peso com ENQ, como as outras famílias', () {
      // Estava EOT (0x04), que não é o pedido de peso de nenhum modelo Urano
      // homologado: o botão "Pegar peso" ficava mudo justo nas balanças em
      // modo sob demanda, que são a razão de ele existir.
      expect(UranoProtocol().weightRequest, [0x05]);
    });

    test('abre a porta em 8-N-1, como as outras famílias', () {
      // Dois stop bits com o equipamento transmitindo 8-N-1 dão erro de
      // enquadramento em cada byte: porta aberta e nenhum quadro chegando.
      expect(UranoProtocol().serialConfig, isNull);
    });
  });

  test('forId devolve o protocolo persistido no cadastro', () {
    // `toledo_prt2` é o valor que o modelo do backend grava e que a tela de
    // equipamentos oferece; sem casá-lo aqui, uma Toledo cadastrada caía
    // calada no decodificador genérico.
    expect(ScaleProtocol.forId('toledo_prt2'), isA<ToledoProtocol>());
    expect(ScaleProtocol.forId('toledo'), isA<ToledoProtocol>());
    expect(ScaleProtocol.forId('FILIZOLA'), isA<FilizolaProtocol>());
    expect(ScaleProtocol.forId(' urano '), isA<UranoProtocol>());
    expect(ScaleProtocol.forId(null), isA<GenericNumericProtocol>());
    expect(ScaleProtocol.forId('inexistente'), isA<GenericNumericProtocol>());
  });
}
