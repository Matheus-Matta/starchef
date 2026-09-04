import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/hardware/scale/scale.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_device.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_protocol.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv/core/hardware/scale/scale_transport.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';

/// Transporte em memória: o teste empurra os bytes que o equipamento enviaria.
class FakeTransport implements ScaleTransport {
  final StreamController<List<int>> _controller =
      StreamController<List<int>>.broadcast();
  final List<List<int>> written = [];

  void send(String frame) => _controller.add(utf8.encode(frame));
  void sendBytes(List<int> bytes) => _controller.add(bytes);

  @override
  Future<Stream<List<int>>> open() async => _controller.stream;

  @override
  Future<bool> write(List<int> bytes) async {
    written.add(bytes);
    return true;
  }

  @override
  Future<void> close() async {
    if (!_controller.isClosed) await _controller.close();
  }
}

/// Cadastro como a tela de equipamentos o grava: `protocol` no topo do
/// registro (é campo do modelo) e `baudrate` dentro de `settings`.
Map<String, dynamic> registro({
  String protocol = 'urano',
  String port = 'COM9',
  Map<String, dynamic>? settings,
}) => {
  'id': 'scale-1',
  'name': 'Balança do buffet',
  'port': port,
  'protocol': protocol,
  'auto_print_delay_seconds': 2,
  'settings': settings ?? {'baudrate': 4800},
};

void main() {
  group('ScaleDevice', () {
    test('lê o protocolo do campo do modelo, não de settings', () {
      // Era aqui que a balança Urano se perdia: a estação lia
      // `settings['protocol']`, que a tela de equipamentos nunca preenche, e
      // caía no decodificador genérico sem nada na tela dizer isso.
      final device = ScaleDevice.fromJson(registro());

      expect(device.protocol, isA<UranoProtocol>());
    });

    test('aceita o protocolo gravado à mão em settings', () {
      final device = ScaleDevice.fromJson(
        registro(
          protocol: '',
          settings: {'baudrate': 9600, 'protocol': 'filizola'},
        ),
      );

      expect(device.protocol, isA<FilizolaProtocol>());
    });

    test('resolve porta, baud rate e estabilização de uma vez', () {
      final device = ScaleDevice.fromJson(registro());

      expect(device.port, 'COM9');
      expect(device.baudRate, 4800);
      expect(device.settleDuration, const Duration(seconds: 2));
      expect(device.lockResource, 'scale:COM9');
      expect(device.summary, contains('4800 baud'));
      expect(device.summary, contains('Urano'));
    });

    test('uma balança sem porta diz o que falta cadastrar', () {
      final device = ScaleDevice.fromJson(registro(port: ''));

      expect(device.hasPort, isFalse);
      expect(device.missingConfiguration, contains('porta serial'));
    });
  });

  group('Scale', () {
    late Directory temporaryHome;

    setUp(() async {
      temporaryHome = await Directory.systemTemp.createTemp('starchef-scale');
      AppPaths.overrideDataDirectory(temporaryHome);
    });

    tearDown(() async {
      AppPaths.overrideDataDirectory(null);
      try {
        if (await temporaryHome.exists()) {
          await temporaryHome.delete(recursive: true);
        }
      } on FileSystemException {
        // No Windows uma trava recém-liberada pode segurar o arquivo por
        // alguns instantes; isso não invalida o teste.
      }
    });

    test('lê o peso com o protocolo do cadastro', () async {
      final transport = FakeTransport();
      final scale = Scale.fromJson(
        registro(),
        runtime: ScaleRuntime(transportFactory: (_) => transport),
      );
      addTearDown(scale.close);

      final samples = <ScaleSample>[];
      // Assinar ANTES de abrir é o uso real da estação; um fluxo que só
      // nascesse no `open` perderia estas amostras.
      scale.samples.listen(samples.add);
      expect(await scale.open(), isTrue);

      transport.sendBytes([0x02, ...utf8.encode('002845'), 0x03]);
      await Future<void>.delayed(const Duration(milliseconds: 20));

      expect(samples.single.weightKg, closeTo(2.845, 0.0001));
    });

    test('sem porta cadastrada não abre e explica o que falta', () async {
      final scale = Scale.fromJson(registro(port: ''));
      addTearDown(scale.close);

      expect(await scale.open(), isFalse);
      expect(scale.status.state, ScaleLinkState.disconnected);
      expect(scale.status.message, contains('porta serial'));
    });

    test('encaminha o pedido de peso ao equipamento', () async {
      final transport = FakeTransport();
      final scale = Scale.fromJson(
        registro(),
        runtime: ScaleRuntime(transportFactory: (_) => transport),
      );
      addTearDown(scale.close);
      await scale.open();

      expect(await scale.requestWeight(), ScaleWeightRequest.sent);
      expect(transport.written.single, [0x05]);
    });
  });
}
