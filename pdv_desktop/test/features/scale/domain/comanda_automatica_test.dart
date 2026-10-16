import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv_desktop/features/scale/domain/hands_free_machine.dart';

ScaleSample amostra(double kg) => ScaleSample(
  weightKg: kg,
  raw: '$kg',
  stable: true,
  at: DateTime(2026, 10, 15, 12),
);

void main() {
  late HandsFreeMachine machine;

  setUp(() {
    machine = HandsFreeMachine(commandTimeout: const Duration(seconds: 30))
      ..start(comandaAutomatica: true);
  });

  tearDown(() => machine.dispose());

  test('peso estável lança direto, sem esperar cartão', () {
    final efeitos = machine.onSample(amostra(0.450), pricePerKg: 60);

    expect(machine.state, HandsFreeState.launching);
    expect(efeitos, contains(HandsFreeEffect.launchIntoCommand));
    expect(machine.commandCode, isNull);
  });

  test('a tela mostra a comanda que o servidor escolheu', () {
    machine.onSample(amostra(0.450), pricePerKg: 60);

    machine.onLaunched(comanda: '17');

    expect(machine.state, HandsFreeState.completed);
    expect(machine.commandCode, '17');
  });

  test('cartão lido no modo automático é recusado', () {
    machine.onSample(amostra(0.450), pricePerKg: 60);
    machine.onOrderFailed('Nenhuma comanda livre');

    expect(machine.onCommandRead('42'), [HandsFreeEffect.alertSound]);
    expect(machine.state, HandsFreeState.failed);
  });

  test('tentar de novo relança a MESMA pesagem', () {
    machine.onSample(amostra(0.450), pricePerKg: 60);
    machine.onOrderFailed('Nenhuma comanda livre');

    final efeitos = machine.tentarDeNovo();

    expect(machine.state, HandsFreeState.launching);
    expect(efeitos, [HandsFreeEffect.launchIntoCommand]);
    expect(machine.weighedItem!.weightKg, 0.450);
  });

  test('cancelado com o prato na balança, ele não é lançado de novo', () {
    machine.onSample(amostra(0.450), pricePerKg: 60);
    machine.onOrderFailed('Nenhuma comanda livre');
    machine.cancel();

    final efeitos = machine.onSample(amostra(0.450), pricePerKg: 60);

    expect(efeitos, isNot(contains(HandsFreeEffect.launchIntoCommand)));
    expect(machine.state, HandsFreeState.waitingWeight);
  });

  test('o mesmo prato lançado não vira segunda pesagem', () {
    machine.onSample(amostra(0.450), pricePerKg: 60);
    machine.onLaunched(comanda: '1');
    machine.readyForNext();

    final efeitos = machine.onSample(amostra(0.450), pricePerKg: 60);

    expect(efeitos, isNot(contains(HandsFreeEffect.launchIntoCommand)));
  });
}
