import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv_desktop/features/scale/domain/hands_free_machine.dart';

ScaleSample amostra(double kg) => ScaleSample(
  weightKg: kg,
  raw: '$kg',
  stable: true,
  at: DateTime(2026, 10, 15, 12),
);

/// A proteção do prato lançado não pode TRAVAR a fila.
///
/// Ela existe para o prato que continua na balança não ser cobrado de novo.
/// Mas a balança que só transmite quando o peso MUDA manda cada leitura uma
/// vez: o que chegou enquanto a estação lançava ou mostrava "Pedido lançado"
/// era jogado fora, e a tela voltava em 0 com o prato novo em cima — travada
/// até alguém mexer no prato.
void main() {
  late HandsFreeMachine machine;

  setUp(() {
    machine = HandsFreeMachine(commandTimeout: const Duration(seconds: 30))
      ..start(comandaAutomatica: true);
  });

  tearDown(() => machine.dispose());

  void lancar(double kg) {
    machine.onSample(amostra(kg), pricePerKg: 50);
    machine.onLaunched(comanda: '1');
  }

  test('prato novo posto durante o "Pedido lançado" já é pesado', () {
    lancar(0.480);
    machine.onSample(amostra(0), pricePerKg: 50);
    machine.onSample(amostra(0.735), pricePerKg: 50); // a única leitura dele

    final efeitos = machine.readyForNext(pricePerKg: 50);

    expect(machine.weighedItem?.weightKg, 0.735);
    expect(efeitos, contains(HandsFreeEffect.launchIntoCommand));
  });

  test('prato novo trocado sem zero no meio também', () {
    lancar(0.480);
    machine.onSample(amostra(0.612), pricePerKg: 50);

    machine.readyForNext(pricePerKg: 50);

    expect(machine.weighedItem?.weightKg, 0.612);
  });

  test('o prato lançado que ficou na balança continua protegido', () {
    lancar(0.480);
    machine.onSample(amostra(0.481), pricePerKg: 50);

    final efeitos = machine.readyForNext(pricePerKg: 50);

    expect(efeitos, isNot(contains(HandsFreeEffect.launchIntoCommand)));
    expect(machine.weighedItem, isNull);
    // E a tela já diz QUAL peso está retido, com o "Pesar de novo".
    expect(machine.aguardandoRetirada, isTrue);
    expect(machine.pesoRetido, 0.481);
  });

  test('sem leitura nenhuma durante o aviso, nada muda', () {
    lancar(0.480);

    expect(machine.readyForNext(pricePerKg: 50), isEmpty);
    expect(machine.weighedItem, isNull);
  });

  test('Esc na escolha do produto não prende o prato', () {
    final escolha = HandsFreeMachine(
      commandTimeout: const Duration(seconds: 30),
    )..start(escolherProduto: true);
    addTearDown(escolha.dispose);
    escolha.onSample(amostra(0.5), pricePerKg: 0);
    escolha.cancel();

    final efeitos = escolha.onSample(amostra(0.5), pricePerKg: 0);

    expect(efeitos, contains(HandsFreeEffect.chooseProduct));
  });
}
