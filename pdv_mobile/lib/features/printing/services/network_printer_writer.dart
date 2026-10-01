import 'dart:async';
import 'dart:io';

import '../domain/mobile_printer.dart';

class NetworkPrinterWriter {
  const NetworkPrinterWriter();

  Future<void> testConnection(MobilePrinter printer) async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        printer.host,
        printer.port,
        timeout: printer.timeout,
      );
    } on TimeoutException {
      throw Exception('A impressora ${printer.name} não respondeu a tempo.');
    } on SocketException catch (error) {
      throw Exception(
        'Não foi possível acessar ${printer.name} em '
        '${printer.host}:${printer.port}: ${error.message}',
      );
    } finally {
      if (socket != null) await _close(socket);
    }
  }

  Future<void> write(MobilePrinter printer, List<int> bytes) async {
    Socket? socket;
    try {
      socket = await Socket.connect(
        printer.host,
        printer.port,
        timeout: printer.timeout,
      );
      socket.add(bytes);
      await socket.flush().timeout(printer.timeout);
    } on TimeoutException {
      throw Exception('A impressora ${printer.name} não respondeu a tempo.');
    } on SocketException catch (error) {
      throw Exception(
        'Não foi possível acessar ${printer.name} em '
        '${printer.host}:${printer.port}: ${error.message}',
      );
    } finally {
      if (socket != null) await _close(socket);
    }
  }

  Future<void> _close(Socket socket) async {
    try {
      await socket.close().timeout(const Duration(seconds: 2));
    } on TimeoutException {
      socket.destroy();
    } on SocketException {
      socket.destroy();
    }
  }
}
