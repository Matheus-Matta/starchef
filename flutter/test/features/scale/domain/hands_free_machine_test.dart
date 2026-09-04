import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv/features/scale/domain/hands_free_machine.dart';

ScaleSample sample(double kg, {bool? stable = true, DateTime? at}) =>
    ScaleSample(
      weightKg: kg,
      raw: '$kg',
      stable: stable,
      at: at ?? DateTime(2026, 7, 28, 12),
    );

void main() {
  late HandsFreeMachine machine;

  setUp(() {
    machine = HandsFreeMachine(commandTimeout: const Duration(seconds: 30));
  });

  tearDown(() => machine.dispose());

  test('começa parada e vai para o Estado 1 ao iniciar', () {
    expect(machine.state, HandsFreeState.idle);

    machine.start();

    expect(machine.state, HandsFreeState.waitingWeight);
    expect(machine.weighedItem, isNull);
  });

  test('não avança com o prato vazio', () {
    machine.start();

    machine.onSample(sample(0.001), pricePerKg: 50);

    expect(machine.state, HandsFreeState.waitingWeight);
    expect(machine.weighedItem, isNull);
  });

  test('não avança enquanto o peso oscila', () {
    machine.start();

    machine.onSample(sample(1.2, stable: false), pricePerKg: 50);

    expect(machine.state, HandsFreeState.waitingWeight);
    expect(machine.currentWeightKg, 1.2);
    expect(machine.isStable, isFalse);
  });

  test('peso estável registra o item e pede a comanda', () {
    machine.start();

    final effects = machine.onSample(sample(1.250), pricePerKg: 40);

    expect(machine.state, HandsFreeState.waitingCommand);
    expect(effects, contains(HandsFreeEffect.successSound));
    expect(machine.weighedItem!.weightKg, 1.250);
    expect(machine.weighedItem!.pricePerKg, 40);
    expect(machine.weighedItem!.total, closeTo(50, 0.0001));
  });

  test('o preço é congelado no instante da estabilização', () {
    machine.start();
    machine.onSample(sample(1.0), pricePerKg: 40);

    // Uma nova amostra com preço diferente não altera o item já capturado.
    machine.onSample(sample(1.0), pricePerKg: 99);

    expect(machine.weighedItem!.pricePerKg, 40);
  });

  test('a leitura da comanda dispara a criação do pedido', () {
    machine.start();
    machine.onSample(sample(0.8), pricePerKg: 30);

    final effects = machine.onCommandRead(' 1234 ');

    expect(machine.state, HandsFreeState.creatingOrder);
    expect(machine.commandCode, '1234');
    expect(effects, contains(HandsFreeEffect.createOrder));
  });

  test('leitura fora da etapa é recusada com alerta', () {
    machine.start();

    final effects = machine.onCommandRead('1234');

    expect(machine.state, HandsFreeState.waitingWeight);
    expect(effects, [HandsFreeEffect.alertSound]);
  });

  test('código vazio não avança', () {
    machine.start();
    machine.onSample(sample(0.8), pricePerKg: 30);

    final effects = machine.onCommandRead('   ');

    expect(machine.state, HandsFreeState.waitingCommand);
    expect(effects, [HandsFreeEffect.alertSound]);
  });

  test('sucesso volta ao Estado 1 limpando a operação', () {
    machine.start();
    machine.onSample(sample(0.8), pricePerKg: 30);
    machine.onCommandRead('1234');

    machine.onOrderCreated();
    expect(machine.state, HandsFreeState.completed);

    machine.readyForNext();
    expect(machine.state, HandsFreeState.waitingWeight);
    expect(machine.weighedItem, isNull);
    expect(machine.commandCode, isNull);
    expect(machine.currentWeightKg, 0);
  });

  test('falha preserva a pesagem para uma nova tentativa', () {
    machine.start();
    machine.onSample(sample(0.8), pricePerKg: 30);
    machine.onCommandRead('1234');

    final effects = machine.onOrderFailed('Comanda já fechada.');

    expect(machine.state, HandsFreeState.failed);
    expect(effects, contains(HandsFreeEffect.alertSound));
    // A venda não pode ser descartada por uma recusa do servidor.
    expect(machine.weighedItem!.weightKg, 0.8);
    expect(machine.canAcceptCommand, isTrue);

    machine.onCommandRead('4321');
    expect(machine.state, HandsFreeState.creatingOrder);
    expect(machine.commandCode, '4321');
  });

  group('tempo da comanda', () {
    final start = DateTime(2026, 7, 28, 12);

    test(
      'um único prazo: esgotado, cancela na hora — sem um segundo tempo de espera por trás',
      () {
        // Havia um segundo temporizador fixo (`gracePeriod`, 10s) somado ao
        // configurado: com 30s de prazo, o cancelamento de fato só vinha aos
        // 40s. Configurar N segundos precisa cancelar em N, não em N + algo.
        machine.start();
        machine.onSample(sample(1.0, at: start), pricePerKg: 30);

        expect(machine.tick(start.add(const Duration(seconds: 29))), isEmpty);
        expect(machine.state, HandsFreeState.waitingCommand);

        final cancel = machine.tick(start.add(const Duration(seconds: 30)));

        expect(cancel, [
          HandsFreeEffect.alertSound,
          HandsFreeEffect.operationCancelled,
        ]);
        expect(machine.state, HandsFreeState.waitingWeight);
        expect(machine.weighedItem, isNull);
      },
    );

    test('ler a comanda um instante antes do prazo ainda conclui a venda', () {
      machine.start();
      machine.onSample(sample(1.0, at: start), pricePerKg: 30);
      machine.tick(start.add(const Duration(seconds: 29)));

      final effects = machine.onCommandRead('9876');

      expect(machine.state, HandsFreeState.creatingOrder);
      expect(effects, contains(HandsFreeEffect.createOrder));
    });

    test(
      'depois do prazo a leitura não é mais aceita — a operação já foi cancelada',
      () {
        machine.start();
        machine.onSample(sample(1.0, at: start), pricePerKg: 30);
        machine.tick(start.add(const Duration(seconds: 30)));

        final effects = machine.onCommandRead('9876');

        expect(effects, [HandsFreeEffect.alertSound]);
        expect(machine.commandCode, isNull);
      },
    );

    test('o tempo restante é exposto para a interface', () {
      machine.start();
      machine.onSample(sample(1.0, at: start), pricePerKg: 30);

      final remaining = machine.remainingForCommand(
        start.add(const Duration(seconds: 10)),
      );

      expect(remaining, const Duration(seconds: 20));
    });
  });

  group('peso zerado', () {
    test('por padrão retirar o prato não cancela a operação', () {
      machine.start();
      machine.onSample(sample(1.0), pricePerKg: 30);

      machine.onSample(sample(0.0), pricePerKg: 30);

      expect(machine.state, HandsFreeState.waitingCommand);
      expect(machine.weighedItem, isNotNull);
    });

    test('cancela quando a política de zero está ativada', () {
      final strict = HandsFreeMachine(
        commandTimeout: const Duration(seconds: 30),
        cancelOnZeroDuringCommand: true,
      );
      addTearDown(strict.dispose);
      strict.start();
      strict.onSample(sample(1.0), pricePerKg: 30);

      final effects = strict.onSample(sample(0.0), pricePerKg: 30);

      expect(effects, contains(HandsFreeEffect.operationCancelled));
      expect(strict.state, HandsFreeState.waitingWeight);
      expect(strict.weighedItem, isNull);
    });
  });

  test('cancelamento manual volta ao Estado 1', () {
    machine.start();
    machine.onSample(sample(1.0), pricePerKg: 30);
    machine.addExtra('produto-1', 2);

    final effects = machine.cancel();

    expect(effects, contains(HandsFreeEffect.operationCancelled));
    expect(machine.state, HandsFreeState.waitingWeight);
    expect(machine.extras, isEmpty);
  });

  test('não cancela enquanto o pedido está sendo criado', () {
    machine.start();
    machine.onSample(sample(1.0), pricePerKg: 30);
    machine.onCommandRead('1234');

    machine.cancel();

    expect(machine.state, HandsFreeState.creatingOrder);
  });

  test('extras são acumulados e removidos ao zerar a quantidade', () {
    machine.start();
    machine.onSample(sample(1.0), pricePerKg: 30);

    machine.addExtra('refrigerante', 2);
    expect(machine.extras['refrigerante'], 2);

    machine.addExtra('refrigerante', 0);
    expect(machine.extras.containsKey('refrigerante'), isFalse);
  });
}
