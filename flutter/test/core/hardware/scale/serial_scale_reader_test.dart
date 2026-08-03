import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_protocol.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_transport.dart';
import 'package:starchef_pdv/core/hardware/scale/serial_scale_reader.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';

/// Transporte em memória: o teste empurra os bytes que o equipamento enviaria.
class FakeTransport implements ScaleTransport {
  FakeTransport({this.failure, this.writable = true});

  final ScaleTransportException? failure;

  /// Simula um driver que só permitiu abrir a porta para leitura.
  final bool writable;

  final StreamController<List<int>> _controller =
      StreamController<List<int>>.broadcast();
  final List<List<int>> written = [];
  bool closed = false;
  int openCount = 0;

  void send(String frame) => _controller.add(utf8.encode(frame));

  @override
  Future<Stream<List<int>>> open() async {
    openCount += 1;
    final error = failure;
    if (error != null) throw error;
    closed = false;
    return _controller.stream;
  }

  @override
  Future<bool> write(List<int> bytes) async {
    if (!writable) return false;
    written.add(bytes);
    return true;
  }

  @override
  Future<void> close() async {
    closed = true;
    if (!_controller.isClosed) await _controller.close();
  }
}

void main() {
  late Directory temporaryHome;

  setUp(() async {
    // As travas de periférico gravam no diretório de dados; um destino
    // temporário evita que o teste toque na instalação real da máquina.
    temporaryHome = await Directory.systemTemp.createTemp('starchef-reader');
    AppPaths.overrideDataDirectory(temporaryHome);
  });

  tearDown(() async {
    AppPaths.overrideDataDirectory(null);
    try {
      if (await temporaryHome.exists()) {
        await temporaryHome.delete(recursive: true);
      }
    } on FileSystemException {
      // No Windows uma trava recém-liberada pode manter o arquivo preso por
      // alguns instantes; isso não invalida o teste.
    }
  });

  test('resolve estabilidade quando o protocolo não a informa', () async {
    final transport = FakeTransport();
    final reader = SerialScaleReader(
      portName: 'FAKE1',
      protocol: GenericNumericProtocol(),
      transportFactory: () => transport,
      settleDuration: const Duration(milliseconds: 80),
      stabilityToleranceKg: 0.002,
    );
    addTearDown(reader.dispose);

    final samples = <ScaleSample>[];
    reader.samples.listen(samples.add);
    await reader.start();

    transport.send('1.000\r\n');
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(samples.last.stable, isFalse);

    // Repetir o mesmo valor além da janela de estabilização confirma o peso.
    await Future<void>.delayed(const Duration(milliseconds: 90));
    transport.send('1.000\r\n');
    await Future<void>.delayed(const Duration(milliseconds: 10));
    expect(samples.last.stable, isTrue);
    expect(samples.last.weightKg, closeTo(1.0, 0.0001));
  });

  test('uma variação acima da tolerância reinicia a estabilização', () async {
    final transport = FakeTransport();
    final reader = SerialScaleReader(
      portName: 'FAKE2',
      protocol: GenericNumericProtocol(),
      transportFactory: () => transport,
      settleDuration: const Duration(milliseconds: 60),
      stabilityToleranceKg: 0.002,
    );
    addTearDown(reader.dispose);

    final samples = <ScaleSample>[];
    reader.samples.listen(samples.add);
    await reader.start();

    transport.send('1.000\r\n');
    await Future<void>.delayed(const Duration(milliseconds: 70));
    transport.send('1.500\r\n');
    await Future<void>.delayed(const Duration(milliseconds: 10));

    expect(samples.last.weightKg, closeTo(1.5, 0.0001));
    expect(samples.last.stable, isFalse);
  });

  test('a instabilidade informada pelo protocolo prevalece', () async {
    final transport = FakeTransport();
    final reader = SerialScaleReader(
      portName: 'FAKE3',
      protocol: ToledoProtocol(),
      transportFactory: () => transport,
      settleDuration: Duration.zero,
    );
    addTearDown(reader.dispose);

    final samples = <ScaleSample>[];
    reader.samples.listen(samples.add);
    await reader.start();

    // Mesmo com o valor repetido e a janela zerada, o bit de movimento do
    // equipamento impede a confirmação.
    transport.send('I001250');
    await Future<void>.delayed(const Duration(milliseconds: 10));
    transport.send('I001250');
    await Future<void>.delayed(const Duration(milliseconds: 10));

    expect(samples.last.stable, isFalse);
  });

  test('publica porta ocupada quando a abertura é recusada', () async {
    final transport = FakeTransport(
      failure: const ScaleTransportException('COM3 ocupada.', portBusy: true),
    );
    final reader = SerialScaleReader(
      portName: 'COM3',
      protocol: GenericNumericProtocol(),
      transportFactory: () => transport,
    );
    addTearDown(reader.dispose);

    await reader.start();

    expect(reader.status.state, ScaleLinkState.portBusy);
    expect(reader.status.message, contains('ocupada'));
  });

  test('a segunda janela não abre a mesma porta', () async {
    final first = SerialScaleReader(
      portName: 'COM7',
      protocol: GenericNumericProtocol(),
      transportFactory: FakeTransport.new,
      ownerDetail: 'Janela 1',
    );
    addTearDown(first.dispose);
    await first.start();
    expect(first.status.state, isNot(ScaleLinkState.portBusy));

    final second = SerialScaleReader(
      portName: 'COM7',
      protocol: GenericNumericProtocol(),
      transportFactory: FakeTransport.new,
      ownerDetail: 'Janela 2',
    );
    addTearDown(second.dispose);
    await second.start();

    expect(second.status.state, ScaleLinkState.portBusy);
    // A mensagem precisa dizer quem detém o equipamento, senão o operador não
    // sabe qual janela fechar.
    expect(second.status.message, contains('Janela 1'));
  });

  group('pegar peso (emergência)', () {
    test('envia o pedido ao equipamento', () async {
      final transport = FakeTransport();
      final reader = SerialScaleReader(
        portName: 'COM11',
        protocol: ToledoProtocol(),
        transportFactory: () => transport,
      );
      addTearDown(reader.dispose);
      await reader.start();

      final result = await reader.requestWeight();

      expect(result, ScaleWeightRequest.sent);
      // ENQ: é assim que uma balança em modo sob demanda responde.
      expect(transport.written.single, [0x05]);
    });

    test('avisa quando a porta abriu somente para leitura', () async {
      final transport = FakeTransport(writable: false);
      final reader = SerialScaleReader(
        portName: 'COM12',
        protocol: GenericNumericProtocol(),
        transportFactory: () => transport,
      );
      addTearDown(reader.dispose);
      await reader.start();

      final result = await reader.requestWeight();

      // Nada é inventado: o operador precisa saber que o pedido não saiu.
      expect(result, ScaleWeightRequest.writeNotSupported);
      expect(transport.written, isEmpty);
    });

    test('reabre a porta quando o canal caiu antes de pedir', () async {
      var opened = 0;
      final transports = <FakeTransport>[];
      final reader = SerialScaleReader(
        portName: 'COM13',
        protocol: GenericNumericProtocol(),
        transportFactory: () {
          opened += 1;
          final transport = FakeTransport();
          transports.add(transport);
          return transport;
        },
      );
      addTearDown(reader.dispose);
      await reader.start();
      expect(opened, 1);

      // Sem nenhuma leitura, o estado ainda é "conectando": o pedido deve
      // reabrir o canal em vez de assumir que está tudo bem.
      final result = await reader.requestWeight();

      expect(result, ScaleWeightRequest.sent);
      expect(opened, 2);
      expect(transports.first.closed, isTrue);
      expect(transports.last.written.single, [0x05]);
    });

    test('a resposta ainda passa pela regra de estabilidade', () async {
      // O pedido reabre a porta, então a fábrica precisa entregar um canal
      // novo a cada abertura — como acontece com a porta serial real.
      final transports = <FakeTransport>[];
      final reader = SerialScaleReader(
        portName: 'COM14',
        protocol: GenericNumericProtocol(),
        transportFactory: () {
          final transport = FakeTransport();
          transports.add(transport);
          return transport;
        },
        settleDuration: const Duration(milliseconds: 80),
      );
      addTearDown(reader.dispose);
      final samples = <ScaleSample>[];
      reader.samples.listen(samples.add);
      await reader.start();

      await reader.requestWeight();
      transports.last.send('2.000\r\n');
      await Future<void>.delayed(const Duration(milliseconds: 10));

      // O botão pede a leitura; ele não confirma peso por conta própria.
      expect(samples.last.weightKg, closeTo(2.0, 0.0001));
      expect(samples.last.stable, isFalse);
    });

    test('não faz nada com a estação parada', () async {
      final reader = SerialScaleReader(
        portName: 'COM15',
        protocol: GenericNumericProtocol(),
        transportFactory: FakeTransport.new,
      );
      addTearDown(reader.dispose);

      expect(await reader.requestWeight(), ScaleWeightRequest.unavailable);
    });
  });

  test('parar libera a porta para outra janela', () async {
    final first = SerialScaleReader(
      portName: 'COM9',
      protocol: GenericNumericProtocol(),
      transportFactory: FakeTransport.new,
    );
    await first.start();
    await first.stop();

    final second = SerialScaleReader(
      portName: 'COM9',
      protocol: GenericNumericProtocol(),
      transportFactory: FakeTransport.new,
    );
    addTearDown(second.dispose);
    await second.start();

    expect(second.status.state, isNot(ScaleLinkState.portBusy));
  });
}
