import 'dart:async';

import 'package:flutter_libserialport/flutter_libserialport.dart';

/// Quanto esperar entre fechar a porta e liberar a memória dela.
///
/// O `SerialPortReader` lê num isolate que fica preso num laço nativo
/// (`sp_wait` com 500 ms de espera). `Isolate.kill()` não interrompe esse
/// laço: ele só termina quando a porta passa a devolver erro, o que acontece
/// depois do `close`. Dois segundos cobrem a espera com folga.
const serialReaderGrace = Duration(seconds: 2);

/// Fecha agora e libera depois — nunca os dois juntos.
///
/// Fechar e liberar em sequência era o que derrubava a Balança Rápida: o
/// isolate do leitor ainda voltava do `sp_wait` e lia a porta já liberada
/// (`sp_free_port`). Acesso a memória liberada não vira exceção em Dart — o
/// Windows encerra o processo, e a janela simplesmente some, sem log.
///
/// Fechar primeiro também devolve a porta ao sistema na hora: reabri-la logo
/// em seguida (trocar de balança, reconectar) funciona sem esperar a folga.
void releaseAfterReader({
  required void Function() close,
  required void Function() free,
  Duration grace = serialReaderGrace,
}) {
  try {
    close();
  } catch (_) {
    // Porta removida do sistema (cabo solto): ainda precisa ser liberada.
  }
  Timer(grace, () {
    try {
      free();
    } catch (_) {
      // Liberar é a última etapa; falhar aqui não pode derrubar a tela.
    }
  });
}

/// [releaseAfterReader] para uma [SerialPort] que teve um leitor.
void releaseReadPort(SerialPort port) => releaseAfterReader(
  close: () {
    if (port.isOpen) port.close();
  },
  free: port.dispose,
);
