import 'dart:async';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../logging/app_logger.dart';

/// O que roda dentro do isolate: `[SendPort saida, int endereco, int esperaMs]`.
typedef EntradaDoLeitor = void Function(List<Object?> args);

/// Lê uma porta serial num isolate que PARA de verdade antes de a porta sumir.
///
/// Substitui a `SerialPortReader` da biblioteca, que derrubava a Balança
/// Rápida no Linux ao pegar o peso. O isolate dela fica preso num laço de
/// chamadas nativas e era encerrado com `Isolate.kill()` no modo padrão, que
/// só age quando o isolate volta ao laço de eventos — e ele nunca volta. Ele
/// seguia lendo a porta já fechada; no Linux o descritor é reaproveitado
/// pela porta reaberta (o "pegar peso" fecha e reabre), a leitura nunca
/// falha, e quando a memória da porta era liberada o processo inteiro caía.
///
/// Aqui: o kill é IMEDIATO (age na próxima volta do laço, em até `esperaMs`)
/// e a porta só é fechada e liberada DEPOIS de o isolate sair. Se ele não
/// sair no prazo, a porta fica sem liberar — vazar memória é melhor do que
/// derrubar o caixa.
class LeitorSerialIsolado {
  LeitorSerialIsolado({
    required this.endereco,
    required this.liberarPorta,
    this.entrada = lerPortaSerial,
    this.esperaMs = 100,
  });

  /// `SerialPort.address`: o isolate reabre a mesma porta por ele.
  final int endereco;

  /// Fecha e libera a porta. Chamado uma vez, só com o isolate já morto.
  final void Function() liberarPorta;
  final EntradaDoLeitor entrada;
  final int esperaMs;

  final _dados = StreamController<Uint8List>();
  final _saida = ReceivePort();
  final _morreu = ReceivePort();
  final _saiu = Completer<void>();
  Future<Isolate>? _iniciando;
  Future<bool>? _parando;

  /// Os bytes que chegam, e o erro da porta (cabo solto) como erro do fluxo.
  Stream<Uint8List> get dados => _dados.stream;

  Future<void> iniciar() async {
    _saida.listen((mensagem) {
      if (_dados.isClosed) return;
      if (mensagem is Uint8List) {
        _dados.add(mensagem);
      } else {
        _dados.addError('$mensagem');
      }
    });
    _morreu.listen((_) {
      if (!_saiu.isCompleted) _saiu.complete();
    });
    _iniciando = Isolate.spawn(
      entrada,
      <Object?>[_saida.sendPort, endereco, esperaMs],
      onExit: _morreu.sendPort,
      debugName: 'leitor-serial',
    );
    await _iniciando;
  }

  /// Mata o isolate, espera ele sair e só então libera a porta.
  ///
  /// Devolve `false` se ele não saiu no prazo (a porta fica sem liberar).
  Future<bool> parar({Duration limite = const Duration(seconds: 3)}) =>
      _parando ??= _parar(limite);

  Future<bool> _parar(Duration limite) async {
    final iniciando = _iniciando;
    if (iniciando != null) {
      try {
        final isolate = await iniciando;
        if (!_saiu.isCompleted) isolate.kill(priority: Isolate.immediate);
      } catch (_) {
        // Não chegou a nascer: não há quem esperar.
        if (!_saiu.isCompleted) _saiu.complete();
      }
    } else if (!_saiu.isCompleted) {
      _saiu.complete();
    }
    final saiu = await _saiu.future
        .then((_) => true)
        .timeout(limite, onTimeout: () => false);
    _saida.close();
    _morreu.close();
    if (!_dados.isClosed) await _dados.close();
    if (saiu) {
      liberarPorta();
    } else {
      AppLogger.instance.error(
        'serial_leitor_nao_parou',
        data: {'esperaMs': esperaMs},
      );
    }
    return saiu;
  }
}

/// O laço do isolate: lê o que chegar, em blocos, até a porta falhar.
///
/// `read` com prazo volta a cada `esperaMs` mesmo sem dado — é o que deixa
/// o kill imediato agir rápido.
void lerPortaSerial(List<Object?> args) {
  final saida = args[0]! as SendPort;
  final porta = SerialPort.fromAddress(args[1]! as int);
  final esperaMs = args[2]! as int;
  while (true) {
    try {
      final bytes = porta.read(512, timeout: esperaMs);
      if (bytes.isNotEmpty) saida.send(bytes);
    } on SerialPortError catch (erro) {
      saida.send(erro.message);
      return;
    }
  }
}
