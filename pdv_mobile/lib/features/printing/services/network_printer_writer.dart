import 'dart:async';
import 'dart:io';

import '../domain/mobile_printer.dart';

class NetworkPrinterWriter {
  const NetworkPrinterWriter();

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
      await socket?.close();
      socket?.destroy();
    }
  }
}
