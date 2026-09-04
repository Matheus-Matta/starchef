import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../../../core/logging/app_logger.dart';
import '../domain/printer_endpoint.dart';
import 'escpos_codec.dart';
import 'printer_device.dart';

/// Falha ao falar com o equipamento, já traduzida para quem opera o caixa.
class PrinterCommunicationException implements Exception {
  const PrinterCommunicationException({
    required this.message,
    required this.recommendedAction,
  });

  final String message;
  final String recommendedAction;

  @override
  String toString() => message;
}

/// Pausas físicas que todo transporte respeita.
///
/// Não são detalhe de implementação de um transporte: são o tempo que o
/// papel e a guilhotina levam, e valem igual para rede, serial e fila do
/// sistema.
class PrintTiming {
  const PrintTiming({
    this.cutDelay = const Duration(milliseconds: 350),
    this.postCutSettleDelay = const Duration(milliseconds: 400),
    Future<void> Function(Duration duration)? delay,
  }) : _delay = delay;

  /// Pausa entre o conteúdo e o comando de corte, só para o transporte
  /// terminar de drenar os bytes já enviados.
  ///
  /// Não é o que resolve o corte no lugar errado — quem faz isso é o avanço
  /// de papel em [EscPosCodec.feedBeforeCutBytes]. Enquanto o avanço era
  /// curto, esta pausa era usada para compensar; com os ~30 mm corretos ela
  /// volta a ser só a margem de drenagem que sempre deveria ter sido.
  final Duration cutDelay;

  /// Pausa mantida com o equipamento ainda reservado, DEPOIS de enviar o
  /// corte — não é o mesmo que [cutDelay] (que é ANTES do corte, para drenar
  /// o conteúdo).
  ///
  /// A guilhotina continua atuando fisicamente por um instante depois do byte
  /// de corte já ter saído da porta. Uma porta serial USB-CDC costuma levar
  /// um tempo para assentar entre um `close()` e o próximo `open()` no mesmo
  /// dispositivo, e uma térmica de rede costuma recusar (ou simplesmente não
  /// responder a) uma nova conexão na 9100 enquanto ainda está processando o
  /// cupom anterior — ela aceita **uma** sessão por vez. Sem essa folga, um
  /// segundo trabalho enfileirado logo em seguida (ex.: a nota de
  /// cancelamento, impressa na mesma impressora da comanda que acabou de
  /// sair) reabria o canal cedo demais: ou o sistema aceitava os bytes na
  /// fila de saída do driver — então nada aqui via erro, o job era marcado
  /// como impresso — mas a impressora nunca chegava a processar esse segundo
  /// cupom, ou a conexão estourava o tempo limite.
  final Duration postCutSettleDelay;

  final Future<void> Function(Duration duration)? _delay;

  Future<void> wait(Duration duration) =>
      (_delay ?? Future<void>.delayed)(duration);
}

/// Como os bytes chegam fisicamente à impressora.
///
/// Cada ligação suportada é uma subclasse: rede (9100), porta serial e fila
/// do sistema operacional. Elas não sabem o que estão imprimindo nem por quê
/// — recebem bytes prontos e respondem por entregar (ou explicar a falha).
abstract class PrinterTransport {
  const PrinterTransport({required this.device, required this.timing});

  final PrinterDevice device;
  final PrintTiming timing;

  PrinterEndpoint get target => device.endpoint;

  /// O transporte precisa de uma checagem prévia do equipamento?
  ///
  /// Em TCP/IP, o próprio envio é a prova de disponibilidade: fazer um
  /// connect/close de teste e reconectar imediatamente faz algumas térmicas
  /// aceitarem a primeira sessão e ignorarem a segunda.
  bool get needsAvailabilityCheck => true;

  Future<void> write(List<int> bytes);

  /// Escolhe o transporte pela ligação cadastrada.
  static PrinterTransport forDevice(
    PrinterDevice device, {
    PrintTiming timing = const PrintTiming(),
    Future<void> Function(PrinterEndpoint target, List<int> bytes)?
    networkWriter,
  }) => switch (device.endpoint.connection) {
    PrinterConnection.network => NetworkPrinterTransport(
      device: device,
      timing: timing,
      writer: networkWriter,
    ),
    PrinterConnection.serial => SerialPrinterTransport(
      device: device,
      timing: timing,
    ),
    PrinterConnection.spool => SpoolPrinterTransport(
      device: device,
      timing: timing,
    ),
  };
}

/// Impressora de rede, porta 9100 (RAW/JetDirect).
class NetworkPrinterTransport extends PrinterTransport {
  const NetworkPrinterTransport({
    required super.device,
    required super.timing,
    this.writer,
    this.connectAttempts = 3,
    this.retryPause = const Duration(milliseconds: 600),
  });

  /// Escrita alternativa, usada nos testes no lugar do socket real.
  final Future<void> Function(PrinterEndpoint target, List<int> bytes)? writer;

  /// Tentativas de conexão antes de declarar a impressora fora do ar.
  ///
  /// Uma térmica de rede aceita uma sessão por vez: enquanto ela termina de
  /// processar o cupom anterior (ou o cupom de outro terminal), o `connect`
  /// não é recusado — fica sem resposta até estourar o tempo limite. Era o
  /// erro intermitente que aparecia só na impressão automática, quando vários
  /// cupons saem em rajada; o teste manual, feito sozinho, nunca disputava a
  /// porta com ninguém.
  final int connectAttempts;

  final Duration retryPause;

  @override
  bool get needsAvailabilityCheck => false;

  @override
  Future<void> write(List<int> bytes) async {
    final custom = writer;
    if (custom != null) {
      await custom(target, bytes);
      return;
    }
    final payload = EscPosCodec.splitCutCommand(bytes, isEscPos: target.isEscPos);
    final socket = await _connect();
    try {
      socket.add(payload.content);
      // `flush` confirma que o buffer de saída do socket foi entregue ao SO.
      await socket.flush().timeout(target.timeout);
      if (payload.cut.isNotEmpty) {
        await timing.wait(timing.cutDelay); // pausa física antes da guilhotina
        socket.add(payload.cut);
        await socket.flush().timeout(target.timeout);
      }
    } finally {
      await socket.close();
    }
    // Segura a reserva do equipamento enquanto a guilhotina atua e a
    // impressora fecha a sessão — ver [PrintTiming.postCutSettleDelay].
    await timing.wait(timing.postCutSettleDelay);
  }

  Future<Socket> _connect() async {
    // Teto de esforço, não só de tentativas: uma recusa imediata (impressora
    // ocupada com o cupom anterior) custa milissegundos e vale repetir; um
    // tempo limite estourado já consumiu os segundos do cadastro, e insistir
    // três vezes deixaria o caixa meio minuto olhando a ampulheta com a
    // impressora desligada na frente dele.
    final deadline = DateTime.now().add(target.timeout * 2);
    Object? lastError;
    var attempts = 0;
    for (var attempt = 1; attempt <= connectAttempts; attempt++) {
      attempts = attempt;
      try {
        return await Socket.connect(
          target.host,
          target.port,
          timeout: target.timeout,
        );
      } on SocketException catch (error) {
        lastError = error;
        AppLogger.instance.info(
          'printer_network_connect_retry',
          data: {
            'printer': device.label,
            'host': '${target.host}:${target.port}',
            'tentativa': attempt,
            'de': connectAttempts,
            'motivo': error.osError?.message ?? error.message,
          },
        );
        if (attempt >= connectAttempts || DateTime.now().isAfter(deadline)) {
          break;
        }
        await timing.wait(retryPause);
      }
    }
    final detail = lastError is SocketException
        ? (lastError.osError?.message ?? lastError.message)
        : '$lastError';
    throw PrinterCommunicationException(
      message:
          'Falha ao comunicar com ${device.label} em '
          '${target.host}:${target.port} depois de $attempts '
          '${attempts == 1 ? 'tentativa' : 'tentativas'}. Motivo: $detail.',
      recommendedAction:
          'Confira se a impressora está ligada e na rede, e se o IP e a porta '
          'do cadastro estão corretos. Se ela estiver imprimindo outro cupom, '
          'o trabalho sai sozinho na próxima tentativa.',
    );
  }
}

/// Impressora ligada a uma porta serial (COM no Windows, `/dev/tty*`).
///
/// Antes isso passava por um `SerialPort` do .NET via PowerShell, o que
/// prendia a impressão serial ao Windows e ainda embutia os bytes em uma
/// linha de comando. `flutter_libserialport` já é usado pela balança e pelo
/// leitor, então a mesma via serve para a impressora nos dois sistemas.
class SerialPrinterTransport extends PrinterTransport {
  const SerialPrinterTransport({required super.device, required super.timing});

  @override
  Future<void> write(List<int> bytes) async {
    final port = SerialPort(target.endpoint);
    // O passo é registrado para a mensagem de erro dizer ONDE falhou: abrir,
    // configurar e escrever têm causas e soluções completamente diferentes,
    // e "Argumento inválido" sozinho não distingue nenhuma delas.
    var step = 'abrir';
    try {
      // Alguns drivers COM virtuais do Windows rejeitam um handle aberto
      // somente para escrita com ERROR_INVALID_HANDLE, embora aceitem o
      // modo leitura/escrita usado pelas APIs e ferramentas nativas do
      // sistema.
      if (!port.openReadWrite()) {
        throw communicationError(
          step,
          SerialPort.lastError?.message ?? 'porta ocupada ou inexistente',
        );
      }
      step = 'configurar';
      port.config = SerialPortConfig()
        ..baudRate = target.baudRate
        ..bits = 8
        ..parity = SerialPortParity.none
        ..stopBits = 1;
      final payload = EscPosCodec.splitCutCommand(
        bytes,
        isEscPos: target.isEscPos,
      );
      step = 'enviar o cupom';
      _writeAll(port, payload.content);
      _settle(port);
      if (payload.cut.isNotEmpty) {
        await timing.wait(timing.cutDelay); // pausa física antes da guilhotina
        step = 'enviar o corte';
        _writeAll(port, payload.cut);
        _settle(port);
        // Mantém a porta aberta e o equipamento reservado até a guilhotina
        // acabar de atuar — ver [PrintTiming.postCutSettleDelay].
        await timing.wait(timing.postCutSettleDelay);
      }
    } on SerialPortError catch (error) {
      throw communicationError(step, error.message);
    } finally {
      if (port.isOpen) port.close();
      port.dispose();
    }
  }

  /// Aguarda o driver esvaziar o buffer de saída — quando ele souber dizer.
  ///
  /// `drain` (`tcdrain`) e `bytesToWrite` (`TIOCOUTQ`) são **confirmação**, não
  /// a escrita em si. Impressoras USB que aparecem como CDC-ACM
  /// (`/dev/ttyACM*`) costumam não implementar essas duas chamadas e devolvem
  /// "Argumento inválido" — e abortar aí descartava como falha um cupom que já
  /// tinha sido entregue à porta. Por isso a falha aqui só é registrada.
  void _settle(SerialPort port) {
    try {
      port.drain();
      final remaining = port.bytesToWrite;
      if (remaining > 0) {
        AppLogger.instance.warning(
          'serial_write_buffer_not_empty',
          data: {'port': target.endpoint, 'bytes': remaining},
        );
      }
    } on SerialPortError catch (error) {
      AppLogger.instance.info(
        'serial_drain_unsupported',
        data: {'port': target.endpoint, 'message': error.message},
      );
    }
  }

  void _writeAll(SerialPort port, List<int> bytes) {
    if (bytes.isEmpty) return;
    final written = port.write(
      Uint8List.fromList(bytes),
      timeout: target.timeout.inMilliseconds,
    );
    if (written < bytes.length) {
      throw communicationError(
        'enviar dados para',
        'foram aceitos apenas $written de ${bytes.length} bytes',
      );
    }
  }

  @visibleForTesting
  PrinterCommunicationException communicationError(String step, String reason) {
    final available = SerialPort.availablePorts;
    final detected = available.isEmpty ? 'nenhuma' : available.join(', ');
    return PrinterCommunicationException(
      message:
          'Falha ao $step a porta ${target.endpoint} '
          '(${target.baudRate} baud, 8N1). Motivo: $reason. '
          'Portas seriais detectadas: $detected.',
      recommendedAction: Platform.isWindows
          ? 'Se a impressora funciona no Teste do Windows, escolha o tipo '
                'Windows / USB e selecione o nome da impressora instalada. '
                'Use Porta serial somente para acesso direto à COM; nesse '
                'caso, feche outros programas que possam estar usando '
                '${target.endpoint} e confirme a velocidade no manual.'
          : 'Feche outros programas que possam estar usando '
                '${target.endpoint} e confirme a porta e a velocidade no manual.',
    );
  }
}

/// Impressora instalada na fila do sistema operacional (Windows/CUPS).
///
/// Esta é a única rota que ainda depende de ferramenta externa, porque não
/// existe API de spool portátil.
///
/// Uma térmica cadastrada como ESC/POS vai por RAW: o driver gráfico
/// (`Out-Printer`, GDI) reinterpreta o cupom pelo tamanho de papel
/// configurado no Windows e descarta os comandos de avanço e corte — é ele o
/// motivo de a nota sair cortada no meio mesmo com o avanço correto no fluxo.
/// No Windows, RAW exige a API do spooler (`winspool.drv`) com o tipo de dado
/// `RAW`, chamada por um script PowerShell temporário — passar o C# inline em
/// `-Command` seria refém do escape de aspas. No CUPS, `lp -o raw` já faz o
/// mesmo. Uma impressora comum (não ESC/POS) segue pelo driver gráfico, com o
/// texto puro que [EscPosCodec.rawTransportBytes] produz quando
/// `isEscPos: false`.
class SpoolPrinterTransport extends PrinterTransport {
  const SpoolPrinterTransport({required super.device, required super.timing});

  bool get _raw => target.isEscPos;

  @override
  Future<void> write(List<int> bytes) async {
    final stamp = DateTime.now().microsecondsSinceEpoch;
    final separator = Platform.pathSeparator;
    final temp = File(
      '${Directory.systemTemp.path}${separator}starchef-$stamp'
      '${_raw ? '.bin' : '.txt'}',
    );
    await temp.writeAsBytes(bytes, flush: true);
    File? script;
    try {
      final ProcessResult result;
      if (Platform.isWindows) {
        if (_raw) {
          script = File(
            '${Directory.systemTemp.path}${separator}starchef-raw-$stamp.ps1',
          );
          await script.writeAsString(_windowsRawSpoolScript, flush: true);
          result = await Process.run('powershell.exe', [
            '-NoProfile',
            '-NonInteractive',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            script.path,
            '-PrinterName',
            target.endpoint,
            '-FilePath',
            temp.path,
          ]).timeout(const Duration(seconds: 30));
        } else {
          final safePath = temp.path.replaceAll("'", "''");
          final safePrinter = target.endpoint.replaceAll("'", "''");
          result = await Process.run('powershell.exe', [
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            "Get-Content -LiteralPath '$safePath' -Raw | "
                "Out-Printer -Name '$safePrinter'",
          ]).timeout(const Duration(seconds: 20));
        }
      } else {
        result = await Process.run('lp', [
          '-d',
          target.endpoint,
          if (_raw) ...['-o', 'raw'],
          // `--` encerra as opções para que um nome iniciado por `-` não vire
          // outra flag do `lp`.
          '--',
          temp.path,
        ]).timeout(const Duration(seconds: 20));
      }
      if (result.exitCode != 0) {
        final detail = '${result.stderr}'.trim().isEmpty
            ? '${result.stdout}'.trim()
            : '${result.stderr}'.trim();
        throw ProcessException(
          Platform.isWindows ? 'powershell.exe' : 'lp',
          const [],
          detail.isEmpty
              ? 'A fila de impressão recusou o trabalho${_raw ? ' RAW' : ''}.'
              : detail,
          result.exitCode,
        );
      }
    } finally {
      if (await temp.exists()) await temp.delete();
      if (script != null && await script.exists()) await script.delete();
    }
  }
}

/// Script que entrega bytes crus à fila de impressão do Windows.
///
/// `Out-Printer` passa pelo driver gráfico, que reescreve o cupom conforme o
/// tamanho de papel do Windows e descarta avanço e corte. A API do spooler
/// com tipo de dado `RAW` entrega os bytes exatamente como foram montados —
/// é o mesmo `RawPrinterHelper` que a documentação da Microsoft descreve.
///
/// Fica em arquivo temporário, e não em `-Command`, para o C# não depender do
/// escape de aspas do PowerShell. A linha `'@` precisa começar na coluna 0.
const _windowsRawSpoolScript = r'''
param([Parameter(Mandatory=$true)][string]$PrinterName,
      [Parameter(Mandatory=$true)][string]$FilePath)
$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class StarchefRawPrinter
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private class DOCINFOW
    {
        [MarshalAs(UnmanagedType.LPWStr)] public string pDocName;
        [MarshalAs(UnmanagedType.LPWStr)] public string pOutputFile;
        [MarshalAs(UnmanagedType.LPWStr)] public string pDataType;
    }

    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool OpenPrinter(string src, out IntPtr hPrinter, IntPtr pd);

    [DllImport("winspool.drv", SetLastError = true)]
    private static extern bool ClosePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool StartDocPrinter(IntPtr hPrinter, int level,
        [In, MarshalAs(UnmanagedType.LPStruct)] DOCINFOW di);

    [DllImport("winspool.drv", SetLastError = true)]
    private static extern bool EndDocPrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true)]
    private static extern bool StartPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true)]
    private static extern bool EndPagePrinter(IntPtr hPrinter);

    [DllImport("winspool.drv", SetLastError = true)]
    private static extern bool WritePrinter(IntPtr hPrinter, IntPtr pBytes,
        int dwCount, out int dwWritten);

    public static void Send(string printerName, byte[] bytes)
    {
        IntPtr hPrinter;
        if (!OpenPrinter(printerName, out hPrinter, IntPtr.Zero))
        {
            throw new Exception("Nao foi possivel abrir a impressora '" +
                printerName + "' (erro " + Marshal.GetLastWin32Error() + ").");
        }
        try
        {
            DOCINFOW di = new DOCINFOW();
            di.pDocName = "StarChef Cupom";
            di.pDataType = "RAW";
            if (!StartDocPrinter(hPrinter, 1, di))
            {
                throw new Exception("StartDocPrinter falhou (erro " +
                    Marshal.GetLastWin32Error() + ").");
            }
            try
            {
                if (!StartPagePrinter(hPrinter))
                {
                    throw new Exception("StartPagePrinter falhou (erro " +
                        Marshal.GetLastWin32Error() + ").");
                }
                try
                {
                    IntPtr buffer = Marshal.AllocCoTaskMem(bytes.Length);
                    try
                    {
                        Marshal.Copy(bytes, 0, buffer, bytes.Length);
                        int written;
                        if (!WritePrinter(hPrinter, buffer, bytes.Length, out written))
                        {
                            throw new Exception("WritePrinter falhou (erro " +
                                Marshal.GetLastWin32Error() + ").");
                        }
                        if (written != bytes.Length)
                        {
                            throw new Exception("A fila aceitou apenas " + written +
                                " de " + bytes.Length + " bytes.");
                        }
                    }
                    finally { Marshal.FreeCoTaskMem(buffer); }
                }
                finally { EndPagePrinter(hPrinter); }
            }
            finally { EndDocPrinter(hPrinter); }
        }
        finally { ClosePrinter(hPrinter); }
    }
}
'@

[StarchefRawPrinter]::Send($PrinterName, [System.IO.File]::ReadAllBytes($FilePath))
''';
