import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

/// Falha ao abrir o canal com a balança.
class ScaleTransportException implements Exception {
  const ScaleTransportException(this.message, {this.portBusy = false});

  final String message;

  /// A porta existe, mas já está reservada por outro processo.
  final bool portBusy;

  @override
  String toString() => message;
}

/// Canal de bytes com a balança física.
///
/// A abstração existe para que a máquina de leitura seja testável sem um
/// equipamento conectado — os testes injetam um transporte de memória.
abstract interface class ScaleTransport {
  /// Abre o canal e devolve o fluxo bruto de bytes.
  Future<Stream<List<int>>> open();

  /// Envia bytes ao equipamento, quando o canal permitir escrita.
  ///
  /// Devolve `false` se o canal foi aberto somente para leitura — algumas
  /// portas e drivers recusam a abertura em modo leitura/escrita, e nesse caso
  /// o leitor continua funcionando com balanças de transmissão contínua.
  Future<bool> write(List<int> bytes);

  Future<void> close();
}

/// Porta serial real (COM no Windows, `/dev/tty*` no Linux).
class SerialScaleTransport implements ScaleTransport {
  SerialScaleTransport({
    required this.portName,
    required this.baudRate,
    this.parity,
    this.stopBits,
  });

  final String portName;
  final int baudRate;
  final dynamic parity;
  final int? stopBits;

  SerialPort? _port;
  SerialPortReader? _reader;
  bool _writable = false;

  /// Portas seriais disponíveis no sistema.
  static List<String> availablePorts() {
    try {
      return SerialPort.availablePorts;
    } on SerialPortError {
      return const [];
    }
  }

  @override
  Future<Stream<List<int>>> open() async {
    final port = SerialPort(portName);
    try {
      // Tenta leitura/escrita primeiro para poder pedir o peso a balanças que
      // só respondem sob comando. Se o driver recusar esse modo, cai para
      // somente leitura: as balanças de transmissão contínua seguem
      // funcionando, só o botão de pegar peso fica indisponível.
      _writable = port.openReadWrite();
      if (!_writable && !port.openRead()) {
        final error = SerialPort.lastError;
        throw ScaleTransportException(
          'Não foi possível abrir $portName: '
          '${error?.message ?? 'porta ocupada ou indisponível'}.',
          // Sem um código específico do sistema, tratamos qualquer recusa de
          // abertura como porta em uso: é a causa real na esmagadora maioria
          // dos casos e leva o operador à verificação certa.
          portBusy: true,
        );
      }
      port.config = SerialPortConfig()
        ..baudRate = baudRate
        ..bits = 8
        ..parity = parity ?? SerialPortParity.none
        ..stopBits = stopBits ?? 1;
      final reader = SerialPortReader(port);
      _port = port;
      _reader = reader;
      return reader.stream;
    } on ScaleTransportException {
      _disposePort(port);
      rethrow;
    } on SerialPortError catch (error) {
      _disposePort(port);
      throw ScaleTransportException(
        'Falha ao configurar $portName: ${error.message}.',
      );
    }
  }

  @override
  Future<bool> write(List<int> bytes) async {
    final port = _port;
    if (port == null || !_writable || !port.isOpen) return false;
    try {
      port.write(Uint8List.fromList(bytes), timeout: 500);
      port.drain();
      return true;
    } on SerialPortError {
      return false;
    }
  }

  @override
  Future<void> close() async {
    _reader?.close();
    _reader = null;
    _writable = false;
    final port = _port;
    _port = null;
    if (port != null) _disposePort(port);
  }

  static void _disposePort(SerialPort port) {
    try {
      if (port.isOpen) port.close();
    } catch (_) {
      // Uma porta já removida do sistema não impede o encerramento.
    }
    port.dispose();
  }
}
