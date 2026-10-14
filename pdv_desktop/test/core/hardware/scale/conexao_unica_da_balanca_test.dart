import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_protocol.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/scale_transport.dart';
import 'package:starchef_pdv_desktop/core/hardware/scale/serial_scale_reader.dart';
import 'package:starchef_pdv_desktop/core/storage/app_paths.dart';

/// "A balança fechando sozinha": UMA conexão por vez, e a sequência de eventos
/// registrada para saber o que aconteceu.
///
/// A porta serial só aceita um dono. Duas aberturas ao mesmo tempo (a
/// reconexão automática e o "pegar peso" do operador) disputavam a porta, e a
/// perdedora derrubava a vencedora ao desistir.
class TransporteLento implements ScaleTransport {
  TransporteLento({this.demora = const Duration(milliseconds: 80)});

  final Duration demora;
  int aberturas = 0;
  int fechamentos = 0;
  StreamController<List<int>> _canal = StreamController<List<int>>();

  void falhar() {
    _canal.addError('cabo solto');
    unawaited(_canal.close());
  }

  @override
  Future<Stream<List<int>>> open() async {
    aberturas += 1;
    await Future<void>.delayed(demora);
    // `sync`: erro e fim chegam no mesmo instante, como na porta real que
    // some do sistema — antes de a primeira falha terminar de desmontar.
    _canal = StreamController<List<int>>(sync: true);
    return _canal.stream;
  }

  @override
  Future<bool> write(List<int> bytes) async => true;

  @override
  Future<void> close() async {
    fechamentos += 1;
    if (!_canal.isClosed) await _canal.close();
  }
}

void main() {
  late Directory temporaria;

  setUp(() async {
    temporaria = await Directory.systemTemp.createTemp('starchef-conexao');
    AppPaths.overrideDataDirectory(temporaria);
  });

  tearDown(() async {
    AppPaths.overrideDataDirectory(null);
    try {
      await temporaria.delete(recursive: true);
    } on FileSystemException {
      // A trava recém-liberada pode prender o arquivo por um instante.
    }
  });

  SerialScaleReader leitor(TransporteLento transporte, String porta) {
    final reader = SerialScaleReader(
      portName: porta,
      protocol: GenericNumericProtocol(),
      transportFactory: () => transporte,
    );
    addTearDown(reader.dispose);
    return reader;
  }

  test('start repetido nao abre a porta de novo', () async {
    final transporte = TransporteLento();
    final reader = leitor(transporte, 'UNI1');

    await Future.wait([reader.start(), reader.start(), reader.start()]);

    expect(transporte.aberturas, 1);
  });

  test('pegar peso durante a abertura nao abre uma segunda vez', () async {
    final transporte = TransporteLento();
    final reader = leitor(transporte, 'UNI2');

    final abrindo = reader.start();
    await Future<void>.delayed(const Duration(milliseconds: 10));
    await Future.wait([abrindo, reader.requestWeight()]);

    expect(transporte.aberturas, 1);
  });

  test('um cabo solto agenda UMA reconexao', () async {
    final transporte = TransporteLento(demora: Duration.zero);
    final reader = leitor(transporte, 'UNI3');
    await reader.start();

    transporte.falhar();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(reader.eventos.where((e) => e == 'reconexao_agendada').length, 1);
  });

  test('parar pelo operador cancela a reconexao pendente', () async {
    final transporte = TransporteLento(demora: Duration.zero);
    final reader = leitor(transporte, 'UNI4');
    await reader.start();
    transporte.falhar();
    await Future<void>.delayed(const Duration(milliseconds: 20));

    await reader.stop();
    // A primeira reconexão viria em 1 s.
    await Future<void>.delayed(const Duration(milliseconds: 1300));

    expect(transporte.aberturas, 1);
  });

  test('a sequencia de eventos fica registrada', () async {
    final transporte = TransporteLento(demora: Duration.zero);
    final reader = leitor(transporte, 'UNI5');
    await reader.start();
    transporte.falhar();
    await Future<void>.delayed(const Duration(milliseconds: 20));
    await reader.stop();

    expect(reader.eventos, [
      'criado',
      'abrindo',
      'aberto',
      'erro',
      'fechado',
      'reconexao_agendada',
      'parado',
    ]);
  });

  test('pedir o peso com a balanca em silencio NAO reabre a porta', () async {
    // A Balança Rápida pede o peso SOZINHA (v3.0.88) quando a tela fica em
    // 0 kg. Com a balança em silêncio ("sem resposta", porta aberta), o
    // pedido fechava e reabria a porta a cada vez — o caminho da queda. Até
    // a v3.0.87 só o botão pedia, e a porta nunca era reaberta à toa.
    final transporte = TransporteLento(demora: Duration.zero);
    final reader = SerialScaleReader(
      portName: 'UNI6',
      protocol: GenericNumericProtocol(),
      transportFactory: () => transporte,
      silenceTimeout: const Duration(milliseconds: 50),
    );
    addTearDown(reader.dispose);
    await reader.start();
    await Future<void>.delayed(const Duration(milliseconds: 1300));
    expect(reader.status.state, ScaleLinkState.noResponse);

    final pedido = await reader.requestWeight();

    expect(pedido, ScaleWeightRequest.sent);
    expect(transporte.aberturas, 1);
    expect(transporte.fechamentos, 0);
  });
}
