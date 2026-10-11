import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv_desktop/features/scale/domain/hands_free_machine.dart';

/// Ao voltar para a tela de pesagem com o prato ainda na balança, o peso
/// ficava em 0 kg.
///
/// A volta zera o peso da tela, e a balança que só transmite quando o peso
/// MUDA não manda nada: o prato está parado. Sem amostra nova, nada aparecia
/// até alguém mexer no prato ou apertar "Pedir peso".
void main() {
  final inicio = DateTime(2026, 10, 11, 12);
  DateTime em(int ms) => inicio.add(Duration(milliseconds: ms));
  ScaleSample amostra(double kg, int ms, {bool stable = true}) =>
      ScaleSample(weightKg: kg, raw: '$kg', stable: stable, at: em(ms));

  late HandsFreeMachine maquina;

  setUp(() {
    maquina = HandsFreeMachine(commandTimeout: const Duration(seconds: 30));
  });
  tearDown(() => maquina.dispose());

  test('em zero sem amostra por 1 segundo, pede o peso a balanca', () {
    maquina.start();

    expect(maquina.tick(em(0)), isEmpty);
    expect(maquina.tick(em(900)), isEmpty);
    expect(maquina.tick(em(1000)), contains(HandsFreeEffect.fetchWeight));
  });

  test('ao voltar do pedido lancado, tambem pede o peso', () {
    maquina.start();
    maquina.onSample(amostra(0.400, 0), pricePerKg: 50);
    maquina.onCommandRead('15');
    maquina.onLaunched();
    maquina.onSample(amostra(0, 500), pricePerKg: 50); // prato retirado

    maquina.readyForNext();

    maquina.tick(em(3000));
    expect(maquina.tick(em(4000)), contains(HandsFreeEffect.fetchWeight));
  });

  test('balanca que transmite sem parar nunca e incomodada', () {
    maquina.start();
    for (var ms = 0; ms <= 3000; ms += 200) {
      maquina.onSample(amostra(0, ms), pricePerKg: 50);
      expect(
        maquina.tick(em(ms)),
        isNot(contains(HandsFreeEffect.fetchWeight)),
      );
    }
  });

  test('zero informado pela balanca e zero de verdade: nao insiste', () {
    maquina.start();
    maquina.tick(em(0));
    expect(maquina.tick(em(1000)), contains(HandsFreeEffect.fetchWeight));

    maquina.onSample(amostra(0, 1100), pricePerKg: 50); // resposta: vazio

    expect(maquina.tick(em(5000)), isEmpty);
  });

  test('peso que chegou oscilando e parou de chegar: pede de novo', () {
    maquina.start();
    maquina.onSample(amostra(0.380, 0, stable: false), pricePerKg: 50);

    expect(maquina.tick(em(500)), isEmpty);
    expect(maquina.tick(em(1000)), contains(HandsFreeEffect.fetchWeight));
  });

  test('desiste depois de 3 pedidos sem resposta', () {
    maquina.start();
    var pedidos = 0;
    for (var s = 0; s <= 10; s++) {
      if (maquina.tick(em(s * 1000)).contains(HandsFreeEffect.fetchWeight)) {
        pedidos++;
      }
    }
    expect(pedidos, 3);
  });

  test('prato ja lancado ainda na balanca nao vira pesagem nova', () {
    maquina.start();
    maquina.onSample(amostra(0.400, 0), pricePerKg: 50);
    maquina.onCommandRead('15');
    maquina.onLaunched();
    maquina.readyForNext(); // o prato continua em cima

    maquina.tick(em(1000));
    maquina.tick(em(2000));
    maquina.onSample(amostra(0.400, 2100), pricePerKg: 50); // a resposta

    expect(maquina.state, HandsFreeState.waitingWeight);
    expect(maquina.aguardandoRetirada, isTrue);
    expect(maquina.pesoRetido, 0.400); // a tela avisa, em vez de 0 calado
    expect(maquina.tick(em(6000)), isEmpty);
  });
}
