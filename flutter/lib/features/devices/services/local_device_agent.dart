import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../../../core/hardware/peripheral_lock.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/realtime_client.dart';
import '../../../core/storage/local_preferences.dart';
import '../domain/printer_endpoint.dart';
import 'print_template_cache.dart';

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

enum PrinterAvailabilityPhase {
  checking,
  available,
  unavailable,
  notConfigured,
}

class PrinterAvailability {
  const PrinterAvailability(this.phase, this.message);

  final PrinterAvailabilityPhase phase;
  final String message;

  bool get isAvailable => phase == PrinterAvailabilityPhase.available;
}

/// Agente local de impressão do processo principal.
///
/// Ele processa a fila de trabalhos de impressão do restaurante e mantém os
/// modelos em cache. A leitura da balança **não** passa mais por aqui: quem lê
/// o equipamento é a própria janela que vai usá-lo, abrindo a porta serial
/// diretamente ([SerialScaleReader]). Isso eliminou o lease remoto
/// (`claim-agent`) e a consulta periódica de peso pela API.
///
/// A impressora continua compartilhada entre este agente e a janela da
/// Balança Rápida (processo à parte, com o seu próprio `LocalDeviceAgent`) —
/// por isso [printForPrinter] reserva a porta serial com [PeripheralLock]
/// antes de escrever, a mesma trava que já protegia a balança.
///
/// A fila de impressão não é mais varrida por polling: o backend já publica
/// `model.updated`/`model.created` para qualquer `PrintJob` da conta em
/// `/ws/pdv/<restaurant_id>/` (todo `TenantModel` ganha isso de graça — ver
/// `apps/realtime/signals.py`). O agente assina esse evento e só consulta
/// `/print-jobs/` quando um deles chega, mais uma verificação pontual ao
/// conectar/reconectar o WS, para cobrir o que foi perdido enquanto a conexão
/// estava caída. Modelos de impressão seguem a mesma regra: sem timer,
/// sincroniza no início e a cada reconexão.
class LocalDeviceAgent {
  LocalDeviceAgent({
    required this.api,
    this.preferences,
    Future<bool> Function(PrinterEndpoint target)? availabilityProbe,
    Future<void> Function(Duration duration)? delay,
    Future<void> Function(PrinterEndpoint target, List<int> bytes)?
    networkWriter,
    this.cutDelay = const Duration(milliseconds: 350),
  }) : _availabilityProbe = availabilityProbe,
       _networkWriter = networkWriter,
       _delay = delay ?? Future<void>.delayed;

  /// `GS V 0` — corte total. O byte final aceita tanto `0x00` quanto `'0'`
  /// (0x30) no padrão ESC/POS; mantemos `0x00`, que é o que as térmicas
  /// vendidas aqui já vinham aceitando.
  static const List<int> escPosCutBytes = [0x1d, 0x56, 0x00];

  /// Avanço de papel obrigatório entre a última linha e a guilhotina.
  ///
  /// A lâmina fica 2 a 3 cm acima da cabeça térmica: acionar o corte logo
  /// depois do texto corta o rodapé ao meio — ou empurra o final do cupom
  /// para o começo do próximo. `ESC 3 40` fixa o passo em 40 pontos (5 mm a
  /// 203 dpi) e `ESC d 6` avança seis linhas, ~30 mm, folga suficiente para
  /// o fim do cupom ultrapassar a lâmina em qualquer térmica de 80 mm.
  ///
  /// Um único `ESC d` em vez de vários `LF` soltos é deliberado: foi a
  /// sequência de LFs repetidos que causou o corte duplo na MP-4200 HS.
  static const List<int> escPosFeedBeforeCutBytes = [
    0x1b, 0x33, 40, // ESC 3 40: passo de 40 pontos só para o avanço final.
    0x1b, 0x64, 6, // ESC d 6: seis avanços de linha (~30 mm).
  ];

  static String? code128ValueFromPayload(Map<String, dynamic> payload) {
    final payloadVersion = int.tryParse('${payload['payload_version'] ?? ''}');
    if (payloadVersion != 2) return null;

    final rawBarcode = payload['barcode'];
    if (rawBarcode is! Map) return null;
    final symbology = '${rawBarcode['symbology'] ?? ''}'.trim().toUpperCase();
    final value = '${rawBarcode['value'] ?? ''}'.trim();
    if (symbology != 'CODE128' || value.isEmpty) return null;
    return value;
  }

  /// Produces an ESC/POS `GS k` Code128 command using code set B.
  ///
  /// Code set B is deliberately limited to printable ASCII. Values outside
  /// that range stay available through the explicit text fallback instead of
  /// sending a malformed barcode to the printer.
  static List<int>? escPosCode128Bytes(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) return null;

    final data = <int>[0x7b, 0x42]; // `{B`: select Code128 set B.
    for (final rune in normalized.runes) {
      if (rune < 0x20 || rune > 0x7e) return null;
      if (rune == 0x7b) {
        data.add(0x7b); // A literal `{` is escaped as `{{` in ESC/POS.
      }
      data.add(rune);
    }
    if (data.length > 255) return null;

    return <int>[
      0x0a,
      0x0a,
      0x1b,
      0x61,
      0x01, // ESC a: center.
      0x1d,
      0x48,
      0x02, // GS H: human-readable value below the bars.
      0x1d,
      0x68,
      0x50, // GS h: 80-dot height.
      0x1d,
      0x77,
      0x02, // GS w: module width 2.
      0x1d,
      0x6b,
      0x49,
      data.length,
      ...data,
      0x0a,
      0x1b,
      0x61,
      0x00, // Restore left alignment for following output.
    ];
  }

  /// Extracts the NFC-e QR Code payload (fiscal DANFE print jobs only).
  ///
  /// Mirrors [code128ValueFromPayload]'s payload_version gate — same contract,
  /// different key (`qr_data` instead of a nested `barcode` map), because a
  /// DANFE fiscal job carries a QR Code, not a Code128 barcode.
  static String? qrValueFromPayload(Map<String, dynamic> payload) {
    final payloadVersion = int.tryParse('${payload['payload_version'] ?? ''}');
    if (payloadVersion != 2) return null;
    final value = '${payload['qr_data'] ?? ''}'.trim();
    return value.isEmpty ? null : value;
  }

  /// Produces an ESC/POS `GS ( k` 2D symbol (QR Code) command sequence.
  ///
  /// Standard Epson ESC/POS "Function 165" sequence, supported by the large
  /// majority of ESC/POS-compatible thermal printers (Epson TM series and
  /// most clones — Bematech, Elgin, Daruma etc. implement the same command
  /// set). Model 2, module size 6 dots, error correction level M (recovers
  /// up to ~15% damage) — a reasonable default for a NFC-e DANFE, where the
  /// QR needs to stay scannable on thermal paper that can fade/crease.
  static List<int>? escPosQrCodeBytes(String data) {
    final bytes = utf8.encode(data.trim());
    if (bytes.isEmpty || bytes.length > 700) return null;

    final storeLength = 3 + bytes.length; // cn + fn + m + data
    final pL = storeLength & 0xff;
    final pH = (storeLength >> 8) & 0xff;

    return <int>[
      0x0a,
      0x1b, 0x61, 0x01, // ESC a: center.
      // Select the model: cn=49('1') fn=65('A') n1=model2(50) n2=0.
      0x1d, 0x28, 0x6b, 0x04, 0x00, 0x31, 0x41, 0x32, 0x00,
      // Set module size: cn=49 fn=67('C') n=6.
      0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x43, 0x06,
      // Set error correction level: cn=49 fn=69('E') n=49 (level M).
      0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x45, 0x31,
      // Store the data: cn=49 fn=80('P') m=48('0') + payload.
      0x1d, 0x28, 0x6b, pL, pH, 0x31, 0x50, 0x30,
      ...bytes,
      // Print the symbol: cn=49 fn=81('Q') m=48('0').
      0x1d, 0x28, 0x6b, 0x03, 0x00, 0x31, 0x51, 0x30,
      0x0a,
      0x1b, 0x61, 0x00, // Restore left alignment.
    ];
  }

  static String textWithBarcodeFallback(String content, String? value) {
    final normalized = value?.trim() ?? '';
    if (normalized.isEmpty) return content;
    final alreadyExplicit =
        content.toUpperCase().contains('CODE128') &&
        content.contains(normalized);
    if (alreadyExplicit) return content;

    final separator = content.endsWith('\n') ? '\n' : '\n\n';
    return '$content${separator}COMANDA - CODE128 (TEXTO)\n$normalized';
  }

  /// Builds the exact byte stream sent through raw network or serial links.
  ///
  /// [qrValue] is exclusive to fiscal DANFE jobs (NFC-e QR Code) — a job never
  /// carries both a barcode and a QR value, but both parameters are accepted
  /// independently to keep this a plain byte-stream builder, not a job-type
  /// switch.
  static List<int> rawTransportBytes(
    String content, {
    required bool isEscPos,
    String? barcodeValue,
    String? qrValue,
  }) {
    final barcodeBytes = isEscPos && barcodeValue != null
        ? escPosCode128Bytes(barcodeValue)
        : null;
    final qrBytes = isEscPos && qrValue != null
        ? escPosQrCodeBytes(qrValue)
        : null;
    final printableContent = barcodeBytes == null
        ? textWithBarcodeFallback(content, barcodeValue)
        : content;
    final transportContent = isEscPos
        ? printableContent
        : textWithBottomMargin(printableContent);
    final contentBytes = isEscPos
        ? _readableReceiptBytes(transportContent)
        : utf8.encode(transportContent);
    return <int>[
      ...contentBytes,
      ...?barcodeBytes,
      ...?qrBytes,
      // Margem em branco no fim de toda nota, depois do código de barras e
      // antes do avanço mecânico. É espaço de CONTEÚDO: a folga da guilhotina
      // continua sendo [escPosFeedBeforeCutBytes], que não muda.
      if (isEscPos) ...List<int>.filled(finalBlankLines, 0x0a),
      // Ordem obrigatória para qualquer cupom: conteúdo, avanço até a lâmina
      // e só então a guilhotina — ver [escPosFeedBeforeCutBytes].
      if (isEscPos) ...[...escPosFeedBeforeCutBytes, ...escPosCutBytes],
    ];
  }

  /// Linhas em branco impressas ao final de toda nota, como respiro entre o
  /// último dado e o corte. Não substitui o avanço mecânico da guilhotina.
  static const int finalBlankLines = 5;

  /// Margem inferior do caminho que só aceita texto (driver gráfico do
  /// sistema e transportes não-ESC/POS).
  ///
  /// Sem comando de corte para enviar, o papel precisa subir sozinho antes de
  /// o driver acionar a guilhotina no fim do documento — mesma folga de ~2 a
  /// 3 cm que [escPosFeedBeforeCutBytes] garante no caminho RAW, aqui obtida
  /// com seis linhas em branco.
  static String textWithBottomMargin(String content) =>
      '$content${'\n' * 6}';

  /// Separa o comando de corte para que o transporte possa drenar o conteúdo
  /// antes de enviá-lo. O retorno mantém os avanços de papel junto ao corpo.
  static ({List<int> content, List<int> cut}) splitCutCommand(
    List<int> bytes, {
    required bool isEscPos,
  }) {
    if (!isEscPos || bytes.length < escPosCutBytes.length) {
      return (content: List<int>.from(bytes), cut: const <int>[]);
    }
    final cutStart = bytes.length - escPosCutBytes.length;
    final hasCut =
        List<int>.generate(
          escPosCutBytes.length,
          (index) => bytes[cutStart + index],
        ).join(',') ==
        escPosCutBytes.join(',');
    if (!hasCut) {
      return (content: List<int>.from(bytes), cut: const <int>[]);
    }
    return (content: bytes.sublist(0, cutStart), cut: bytes.sublist(cutStart));
  }

  /// Applies conservative ESC/POS typography that remains readable on both
  /// 58 mm and 80 mm rolls: larger line spacing, emphasized first line and
  /// double-height totals. Width is kept normal so item values are not cut.
  static List<int> _readableReceiptBytes(String content) {
    final result = <int>[
      0x1b, 0x40, // Initialize.
      0x1b, 0x74, 0x02, // ESC t 2: pagina PC850 (padrao brasileiro).
      0x1b, 0x33, 34, // Comfortable line spacing.
      0x1d, 0x4c, 8, 0, // Small left margin.
    ];
    var firstTextLine = true;
    for (final line in content.split('\n')) {
      final normalized = line.trim().toUpperCase();
      final prominent = firstTextLine || normalized.startsWith('TOTAL');
      result.addAll([0x1b, 0x21, prominent ? 0x10 : 0x00]);
      result.addAll(_encodePrintable(line));
      result.add(0x0a);
      if (normalized.isNotEmpty) firstTextLine = false;
    }
    result.addAll([0x1b, 0x21, 0x00]);
    return result;
  }

  /// Reduz o texto a ASCII imprimível antes de enviar à impressora.
  ///
  /// As térmicas em uso não renderizam a página de código estendida: um "Ç"
  /// enviado como byte alto sai como "?" no papel, e a palavra fica pior do
  /// que sem o acento. Trocar pela letra base ("Ç" -> "C", "ã" -> "a") sai
  /// legível em qualquer equipamento, que é o que importa num cupom.
  static List<int> _encodePrintable(String value) {
    const equivalents = <int, String>{
      // Latim acentuado -> letra base.
      0x00c0: 'A', 0x00c1: 'A', 0x00c2: 'A', 0x00c3: 'A', 0x00c4: 'A',
      0x00c5: 'A', 0x00c7: 'C',
      0x00c8: 'E', 0x00c9: 'E', 0x00ca: 'E', 0x00cb: 'E',
      0x00cc: 'I', 0x00cd: 'I', 0x00ce: 'I', 0x00cf: 'I',
      0x00d1: 'N',
      0x00d2: 'O', 0x00d3: 'O', 0x00d4: 'O', 0x00d5: 'O', 0x00d6: 'O',
      0x00d9: 'U', 0x00da: 'U', 0x00db: 'U', 0x00dc: 'U', 0x00dd: 'Y',
      0x00e0: 'a', 0x00e1: 'a', 0x00e2: 'a', 0x00e3: 'a', 0x00e4: 'a',
      0x00e5: 'a', 0x00e7: 'c',
      0x00e8: 'e', 0x00e9: 'e', 0x00ea: 'e', 0x00eb: 'e',
      0x00ec: 'i', 0x00ed: 'i', 0x00ee: 'i', 0x00ef: 'i',
      0x00f1: 'n',
      0x00f2: 'o', 0x00f3: 'o', 0x00f4: 'o', 0x00f5: 'o', 0x00f6: 'o',
      0x00f9: 'u', 0x00fa: 'u', 0x00fb: 'u', 0x00fc: 'u',
      0x00fd: 'y', 0x00ff: 'y',
      0x00c6: 'AE', 0x00e6: 'ae', 0x00df: 'ss',
      0x00aa: 'a', 0x00ba: 'o',
      // Pontuação tipográfica que às vezes chega do template.
      0x00a0: ' ', 0x00b7: '-', 0x00d7: 'x',
      0x2013: '-', 0x2014: '-',
      0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"',
      0x2026: '...', 0x20ac: 'EUR',
    };
    final result = <int>[];
    for (final rune in value.runes) {
      if (rune <= 0x7f) {
        result.add(rune);
        continue;
      }
      // Texto decomposto (NFD) chega como letra + acento combinante. A letra
      // já foi escrita acima; o acento sozinho viraria "?" no papel.
      if (rune >= 0x0300 && rune <= 0x036f) continue;
      final equivalent = equivalents[rune];
      if (equivalent != null) {
        result.addAll(equivalent.codeUnits);
        continue;
      }
      result.add(0x3f);
    }
    return result;
  }

  final ApiClient api;
  final LocalPreferences? preferences;
  final Future<bool> Function(PrinterEndpoint target)? _availabilityProbe;
  final Future<void> Function(PrinterEndpoint target, List<int> bytes)?
  _networkWriter;
  final Future<void> Function(Duration duration) _delay;

  /// Pausa entre o conteúdo e o comando de corte, só para o transporte
  /// terminar de drenar os bytes já enviados.
  ///
  /// Não é o que resolve o corte no lugar errado — quem faz isso é o avanço
  /// de papel em [escPosFeedBeforeCutBytes]. Enquanto o avanço era curto,
  /// esta pausa era usada para compensar; com os ~30 mm corretos ela volta a
  /// ser só a margem de drenagem que sempre deveria ter sido.
  final Duration cutDelay;
  final ValueNotifier<PrinterAvailability> printerAvailability =
      ValueNotifier<PrinterAvailability>(
        const PrinterAvailability(
          PrinterAvailabilityPhase.checking,
          'Verificando impressora...',
        ),
      );
  RealtimeClient? _realtime;
  StreamSubscription<RealtimeEvent>? _eventSubscription;
  StreamSubscription<void>? _connectedSubscription;
  bool _running = false;
  String? _token;
  String? _restaurantId;
  DateTime? _lastTemplateSync;
  DateTime? _lastDeviceSync;
  DateTime? _backoffUntil;
  Future<void>? _deviceSyncInFlight;
  List<Map<String, dynamic>> _printers = const [];
  Timer? _availabilityTimer;
  Timer? _scheduledPrintTimer;
  Timer? _printJobsPollTimer;

  void start({required String token, required String restaurantId}) {
    if (_realtime != null && _token == token && _restaurantId == restaurantId) {
      return;
    }
    _token = token;
    _restaurantId = restaurantId;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _backoffUntil = null;
    _availabilityTimer?.cancel();
    _scheduledPrintTimer?.cancel();
    _scheduledPrintTimer = null;
    _printJobsPollTimer?.cancel();
    printerAvailability.value = const PrinterAvailability(
      PrinterAvailabilityPhase.checking,
      'Verificando impressora...',
    );
    unawaited(refreshPrinterAvailability());
    _availabilityTimer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => unawaited(refreshPrinterAvailability(useCachedDevices: true)),
    );
    // Rede de segurança independente do WS: o evento em tempo real que
    // liberaria a rodada da cozinha pode se perder numa reconexão, e sem
    // isto a impressão automática ficava sem nenhum outro gatilho até o
    // operador tocar em alguma tela que reconsultasse `/print-jobs/` por
    // conta própria.
    _printJobsPollTimer = Timer.periodic(
      const Duration(minutes: 2),
      (_) => unawaited(_guarded(_processPrintJobs)),
    );
    _stopRealtime();
    final realtime = RealtimeClient(
      urlBuilder: () => api.pdvSocketUrl(_restaurantId!),
      headersBuilder: () => {
        'Authorization': 'Bearer ${api.currentAccessToken ?? _token!}',
      },
    );
    _realtime = realtime;
    // Ao (re)conectar, uma verificação pontual cobre o que pode ter mudado
    // enquanto a conexão estava caída — nunca um timer recorrente.
    _connectedSubscription = realtime.onConnected.listen((_) => _onConnected());
    _eventSubscription = realtime.events.listen(_onRealtimeEvent);
    realtime.start();
  }

  void stop() {
    _stopRealtime();
    _availabilityTimer?.cancel();
    _availabilityTimer = null;
    _scheduledPrintTimer?.cancel();
    _scheduledPrintTimer = null;
    _printJobsPollTimer?.cancel();
    _printJobsPollTimer = null;
    _token = null;
    _restaurantId = null;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _backoffUntil = null;
    _deviceSyncInFlight = null;
    _printers = const [];
    printerAvailability.value = const PrinterAvailability(
      PrinterAvailabilityPhase.notConfigured,
      'Impressora desconectada',
    );
  }

  void dispose() {
    stop();
  }

  void _stopRealtime() {
    unawaited(_eventSubscription?.cancel());
    _eventSubscription = null;
    unawaited(_connectedSubscription?.cancel());
    _connectedSubscription = null;
    _realtime?.dispose();
    _realtime = null;
  }

  /// Um `PrintJob` de outro restaurante da mesma conta não interessa a este
  /// agente: o grupo do WS é por conta, não por restaurante.
  static bool isPrintJobEvent(RealtimeEvent event, String? restaurantId) {
    if (event.payload['resource'] != 'printers.printjob') return false;
    final eventRestaurantId = '${event.payload['restaurant_id'] ?? ''}';
    return eventRestaurantId.isEmpty || eventRestaurantId == restaurantId;
  }

  static bool isDeviceConfigurationEvent(
    RealtimeEvent event,
    String? restaurantId,
  ) {
    final resource = '${event.payload['resource'] ?? ''}';
    if (resource != 'printers.printer' && resource != 'printers.scale') {
      return false;
    }
    final eventRestaurantId = '${event.payload['restaurant_id'] ?? ''}';
    return eventRestaurantId.isEmpty || eventRestaurantId == restaurantId;
  }

  void _onRealtimeEvent(RealtimeEvent event) {
    final restaurantId = _restaurantId;
    if (restaurantId == null) return;
    api.applyRealtimeEvent(event, restaurantId: restaurantId);
    if (event.payload['resource'] == 'printers.printjob') {
      // Loga mesmo quando o restaurante não bate: um evento chegando com o
      // restaurant_id errado (ou vazio, quando não deveria estar) explicaria
      // a impressão nunca disparar sem nenhum erro visível na tela.
      AppLogger.instance.info(
        'realtime_printjob_event',
        data: {
          'event_restaurant': event.payload['restaurant_id'],
          'agent_restaurant': restaurantId,
          'matched': isPrintJobEvent(event, restaurantId),
        },
      );
    }
    if (isPrintJobEvent(event, restaurantId)) {
      unawaited(_onPrintJobEvent());
    }
    if (isDeviceConfigurationEvent(event, restaurantId)) {
      _lastDeviceSync = null;
      unawaited(
        _guarded(() async {
          await _syncDevicesIfNeeded();
          await refreshPrinterAvailability(useCachedDevices: true);
        }),
      );
    }
  }

  Future<void> _onConnected() {
    api.notifyRealtimeConnected();
    return _guarded(() {
      // Reconexões instáveis não devem virar rajadas contra o servidor de
      // modelos: uma janela mínima entre sincronizações basta, já que nada
      // muda um template com essa frequência.
      final shouldSyncTemplates =
          _lastTemplateSync == null ||
          DateTime.now().difference(_lastTemplateSync!) >
              const Duration(minutes: 1);
      return Future.wait([
        _processPrintJobs(),
        if (shouldSyncTemplates) _syncTemplates(),
      ]);
    });
  }

  Future<void> _onPrintJobEvent() => _guarded(_processPrintJobs);

  Future<void> _guarded(Future<void> Function() action) async {
    if (_running || _token == null || _restaurantId == null) return;
    if (_backoffUntil case final backoff?
        when DateTime.now().isBefore(backoff)) {
      return;
    }
    _running = true;
    try {
      await action();
    } on ApiException catch (error) {
      if (error.statusCode == 429) {
        final match = RegExp(
          r'available in (\d+) seconds',
          caseSensitive: false,
        ).firstMatch(error.message);
        final seconds = int.tryParse(match?.group(1) ?? '') ?? 60;
        _backoffUntil = DateTime.now().add(Duration(seconds: seconds + 1));
      }
      // O agente tenta novamente no próximo evento, depois do intervalo
      // permitido pela API.
    } catch (_) {
      // O agente é tolerante a falhas: o próximo evento tenta de novo.
    } finally {
      _running = false;
    }
  }

  Future<void> _syncTemplates() async {
    try {
      await PrintTemplateCache(
        api: api,
      ).sync(token: _token!, restaurantId: _restaurantId!);
    } finally {
      _lastTemplateSync = DateTime.now();
    }
  }

  Future<List<Map<String, dynamic>>> _list(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final data = await api.get(path, query: query, accessToken: _token);
    return ((data['results'] ?? const []) as List).cast<Map<String, dynamic>>();
  }

  Future<void> _processPrintJobs() async {
    _scheduledPrintTimer?.cancel();
    _scheduledPrintTimer = null;
    await _syncDevicesIfNeeded();
    final availablePrinters = <String, Map<String, dynamic>>{
      for (final printer in _printers)
        if (PrinterEndpoint.fromJson(printer).isAddressable)
          '${printer['id']}': printer,
    };

    DateTime? nextScheduledAt;
    var attempted = 0;
    for (final status in ['scheduled', 'pending', 'rendered']) {
      final jobs = await _list(
        '/print-jobs/',
        query: {
          'restaurant': _restaurantId,
          'status': status,
          'page_size': 100,
          'ordering': 'created_at',
        },
      );
      // Sem isto, um job pulado (impressora não cadastrada localmente,
      // auto_print desligado, marcado manual_only) desaparecia em silêncio:
      // não havia como saber, sem acesso à tela, se o agente sequer chegou a
      // ver o trabalho.
      AppLogger.instance.info(
        'print_jobs_poll',
        data: {
          'status': status,
          'found': jobs.length,
          'restaurant': _restaurantId,
        },
      );
      for (final job in jobs) {
        if ('${job['status']}' == 'scheduled') {
          final availableAt = DateTime.tryParse(
            '${job['available_at'] ?? ''}',
          )?.toLocal();
          if (availableAt != null && availableAt.isAfter(DateTime.now())) {
            if (nextScheduledAt == null ||
                availableAt.isBefore(nextScheduledAt)) {
              nextScheduledAt = availableAt;
            }
          }
          continue;
        }
        final printer = availablePrinters['${job['printer']}'];
        if (printer == null) {
          AppLogger.instance.warning(
            'print_job_skipped_printer_unavailable',
            data: {'job_id': job['id'], 'printer_id': job['printer']},
          );
          continue;
        }
        final payload = job['payload'] as Map<String, dynamic>? ?? const {};
        if (payload['manual_only'] == true) {
          // Sem este registro, um trabalho marcado como manual sumia sem
          // deixar rastro: "não imprimiu e não deu erro" ficava impossível de
          // diagnosticar sem acesso ao banco.
          AppLogger.instance.info(
            'print_job_skipped_manual_only',
            data: {'job_id': job['id'], 'printer_id': job['printer']},
          );
          continue;
        }
        final isAutomaticWeighTicket = '${job['job_type']}' == 'weigh_ticket';
        if (printer['auto_print'] != true && !isAutomaticWeighTicket) {
          AppLogger.instance.info(
            'print_job_skipped_auto_print_off',
            data: {'job_id': job['id'], 'printer_id': printer['id']},
          );
          continue;
        }
        attempted++;
        var printed = false;
        try {
          final readyText = '${payload['text_content'] ?? ''}'.trim();
          final text = readyText.isNotEmpty
              ? readyText
              : htmlToText('${job['html_content'] ?? ''}');
          if (text.trim().isEmpty) {
            throw const FormatException('O trabalho não possui conteúdo.');
          }
          await printForPrinter(
            printer,
            text,
            barcodeValue: code128ValueFromPayload(payload),
            qrValue: qrValueFromPayload(payload),
          );
          printed = true;
          await api.post(
            '/print-jobs/${job['id']}/mark-printed/',
            body: const {},
            accessToken: _token,
          );
          AppLogger.instance.info(
            'print_job_printed',
            data: {
              'job_id': job['id'],
              'job_type': job['job_type'],
              'printer_id': printer['id'],
            },
          );
        } catch (error) {
          // Se o cupom já saiu, o problema foi só avisar o servidor. Marcar
          // como falha aqui deixaria o trabalho elegível para imprimir de
          // novo no próximo ciclo — a mesma nota saindo duas vezes.
          if (printed) {
            AppLogger.instance.warning(
              'print_job_printed_but_not_confirmed',
              data: {'job_id': job['id'], 'message': '$error'},
            );
            continue;
          }
          AppLogger.instance.error(
            'print_job_failed',
            cause: error,
            data: {
              'job_id': job['id'],
              'job_type': job['job_type'],
              'printer_id': printer['id'],
            },
          );
          await api.post(
            '/print-jobs/${job['id']}/mark-failed/',
            body: {'error': 'Falha no PDV Desktop: $error'},
            accessToken: _token,
          );
        }
      }
    }
    if (nextScheduledAt != null && _token != null) {
      final wait = nextScheduledAt.difference(DateTime.now());
      AppLogger.instance.info(
        'print_jobs_next_scheduled',
        data: {
          'available_at': nextScheduledAt.toIso8601String(),
          'wait_ms': wait.inMilliseconds,
        },
      );
      _scheduledPrintTimer = Timer(
        wait.isNegative
            ? const Duration(milliseconds: 100)
            : wait + const Duration(milliseconds: 150),
        () => unawaited(_guarded(_processPrintJobs)),
      );
    } else if (attempted == 0) {
      AppLogger.instance.info(
        'print_jobs_poll_idle',
        data: {'restaurant': _restaurantId},
      );
    }
  }

  Future<void> printJobManually(
    Map<String, dynamic> job,
    Map<String, dynamic> printer,
  ) async {
    final token = _token;
    if (token == null) {
      throw StateError('O agente local não está autenticado.');
    }
    final jobId = '${job['print_job_id'] ?? job['id'] ?? ''}'.trim();
    if (jobId.isEmpty) {
      throw StateError('Trabalho de impressão inválido.');
    }
    final rawPayload = job['payload'];
    final payload = rawPayload is Map<String, dynamic>
        ? rawPayload
        : const <String, dynamic>{};
    final readyText = '${payload['text_content'] ?? ''}'.trim();
    final text = readyText.isNotEmpty
        ? readyText
        : htmlToText('${job['html'] ?? job['html_content'] ?? ''}');
    if (text.isEmpty) {
      throw StateError('O trabalho não possui conteúdo para impressão.');
    }
    // O papel já ter saído e o servidor não ter sido avisado são coisas
    // diferentes: tratar as duas como "falha na impressão" mostrava erro numa
    // nota que o operador tinha na mão e ainda marcava o trabalho como
    // falho — deixando-o elegível para sair de novo.
    var printed = false;
    try {
      await printForPrinter(
        printer,
        text,
        barcodeValue: code128ValueFromPayload(payload),
        qrValue: qrValueFromPayload(payload),
      );
      printed = true;
      await api.post(
        '/print-jobs/$jobId/mark-printed/',
        body: const {},
        accessToken: token,
      );
    } catch (error) {
      if (printed) {
        AppLogger.instance.warning(
          'print_job_printed_but_not_confirmed',
          data: {'job_id': jobId, 'message': '$error'},
        );
        return;
      }
      await api.post(
        '/print-jobs/$jobId/mark-failed/',
        body: {'error': 'Falha na impressão manual: $error'},
        accessToken: token,
      );
      rethrow;
    }
  }

  /// Envia texto para a fila de impressão do sistema operacional.
  ///
  /// Esta é a única rota que ainda depende de ferramenta externa, porque não
  /// existe API de spool portátil: Windows usa `Out-Printer` do PowerShell e
  /// Linux/macOS usam `lp` do CUPS.
  Future<void> printText(String printerName, String content) async {
    final temp = File(
      '${Directory.systemTemp.path}${Platform.pathSeparator}'
      'starchef-${DateTime.now().microsecondsSinceEpoch}.txt',
    );
    await temp.writeAsString(
      textWithBottomMargin(content),
      encoding: utf8,
      flush: true,
    );
    try {
      final ProcessResult result;
      if (Platform.isWindows) {
        final safePath = temp.path.replaceAll("'", "''");
        final safePrinter = printerName.replaceAll("'", "''");
        result = await Process.run('powershell.exe', [
          '-NoProfile',
          '-NonInteractive',
          '-Command',
          "Get-Content -LiteralPath '$safePath' -Raw | "
              "Out-Printer -Name '$safePrinter'",
        ]).timeout(const Duration(seconds: 20));
      } else {
        // `--` encerra as opções para que um nome iniciado por `-` não vire
        // outra flag do `lp`.
        result = await Process.run('lp', [
          '-d',
          printerName,
          '--',
          temp.path,
        ]).timeout(const Duration(seconds: 20));
      }
      if (result.exitCode != 0) {
        throw ProcessException(
          Platform.isWindows ? 'powershell.exe' : 'lp',
          const [],
          '${result.stderr}'.trim().isEmpty
              ? 'A fila de impressão recusou o trabalho.'
              : '${result.stderr}',
          result.exitCode,
        );
      }
    } finally {
      if (await temp.exists()) await temp.delete();
    }
  }

  /// Envia bytes ESC/POS crus para uma impressora da fila do sistema.
  ///
  /// O driver gráfico (`Out-Printer`, GDI) reinterpreta o cupom pelo tamanho
  /// de papel configurado no Windows e descarta os comandos de avanço e
  /// corte — é ele o motivo de a nota sair cortada no meio mesmo com o
  /// avanço correto no fluxo. RAW entrega os bytes exatamente como montados.
  ///
  /// No Windows isso exige a API do spooler (`winspool.drv`) com o tipo de
  /// dado `RAW`, chamada por um script PowerShell temporário — passar o C#
  /// inline em `-Command` seria refém do escape de aspas. No CUPS,
  /// `lp -o raw` já faz o mesmo.
  Future<void> printRawToSpool(String printerName, List<int> bytes) async {
    final stamp = DateTime.now().microsecondsSinceEpoch;
    final separator = Platform.pathSeparator;
    final temp = File('${Directory.systemTemp.path}${separator}starchef-$stamp.bin');
    await temp.writeAsBytes(bytes, flush: true);
    File? script;
    try {
      final ProcessResult result;
      if (Platform.isWindows) {
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
          printerName,
          '-FilePath',
          temp.path,
        ]).timeout(const Duration(seconds: 30));
      } else {
        result = await Process.run('lp', [
          '-d',
          printerName,
          '-o',
          'raw',
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
              ? 'A fila de impressão recusou o trabalho RAW.'
              : detail,
          result.exitCode,
        );
      }
    } finally {
      if (await temp.exists()) await temp.delete();
      if (script != null && await script.exists()) await script.delete();
    }
  }

  /// Entrega o conteúdo pela via configurada na impressora.
  ///
  /// Rede e serial escrevem os bytes diretamente e funcionam igual em Windows
  /// e Linux; só a fila do sistema depende do utilitário de cada plataforma.
  Future<void> printForPrinter(
    Map<String, dynamic> printer,
    String content, {
    String? barcodeValue,
    String? qrValue,
  }) async {
    // Toda impressão usa o que está no cadastro da impressora — sem override
    // por terminal. O override existia para o caso de o mesmo equipamento
    // receber caminhos diferentes em cada máquina, mas criava a divergência
    // pior: uma porta salva localmente ficava desatualizada em relação ao
    // cadastro, e a impressão real abria um dispositivo diferente do que o
    // teste de conexão abria — teste passando e cupom não saindo.
    final resolvedPrinter = printer;
    final target = PrinterEndpoint.fromJson(resolvedPrinter);
    // O aviso na tela é um só para todas as impressoras do terminal, então
    // precisa dizer QUAL falhou e por quê: "Impressora desconectada" sozinho
    // não distingue o cupom do caixa da comanda da cozinha, nem diz o motivo.
    final label = '${resolvedPrinter['name'] ?? ''}'.trim().isEmpty
        ? target.label
        : '${resolvedPrinter['name']} (${target.label})';
    final missing = target.missingConfiguration;
    if (missing != null) {
      printerAvailability.value = PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        '$label: $missing',
      );
      throw PrinterCommunicationException(
        message: 'Falha ao comunicar com $label. $missing',
        recommendedAction: 'Revise a configuração local da impressora.',
      );
    }

    try {
      // Em TCP/IP, o próprio envio é a prova de disponibilidade. Fazer um
      // connect/close de teste e reconectar imediatamente faz algumas
      // impressoras térmicas aceitarem a primeira sessão e ignorarem a
      // segunda. Serial e spool ainda precisam da checagem prévia local.
      if (target.connection != PrinterConnection.network &&
          !await checkPrinterAvailability(resolvedPrinter)) {
        throw PrinterCommunicationException(
          message: 'Não foi possível abrir $label: dispositivo não encontrado.',
          recommendedAction:
              'Confira o cabo, a energia e a porta configurada. O PDV continuará funcionando normalmente.',
        );
      }

      if (target.connection == PrinterConnection.spool && !target.isEscPos) {
        // Impressora comum na fila do sistema (driver gráfico): só texto,
        // com a margem inferior fazendo o papel do avanço antes do corte.
        await printText(
          target.endpoint,
          textWithBarcodeFallback(content, barcodeValue),
        );
      } else {
        final printBytes = rawTransportBytes(
          content,
          isEscPos: target.isEscPos,
          barcodeValue: barcodeValue,
          qrValue: qrValue,
        );
        if (target.connection == PrinterConnection.spool) {
          // Térmica instalada como impressora do sistema: os bytes ESC/POS
          // vão RAW para a fila, sem passar pelo driver gráfico — é ele que
          // reescreve o cupom pelo tamanho de papel do Windows e ignora o
          // nosso avanço antes da guilhotina.
          await printRawToSpool(target.endpoint, printBytes);
        } else if (target.connection == PrinterConnection.network) {
          final writer = _networkWriter;
          if (writer == null) {
            await _writeToNetworkPrinter(target, printBytes);
          } else {
            await writer(target, printBytes);
          }
        } else {
          await _writeToSerialPrinter(target, printBytes);
        }
      }
      printerAvailability.value = const PrinterAvailability(
        PrinterAvailabilityPhase.available,
        'Impressora disponível',
      );
    } on PrinterCommunicationException catch (error) {
      printerAvailability.value = PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        error.message,
      );
      rethrow;
    } catch (error) {
      final message = 'Falha ao comunicar com $label: $error';
      printerAvailability.value = PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        message,
      );
      throw PrinterCommunicationException(
        message: message,
        recommendedAction:
            'Confira o cabo, a energia e a porta configurada. O PDV continuará funcionando normalmente.',
      );
    }
  }

  Future<void> _writeToNetworkPrinter(
    PrinterEndpoint target,
    List<int> bytes,
  ) async {
    final payload = splitCutCommand(bytes, isEscPos: target.isEscPos);
    final socket = await Socket.connect(
      target.host,
      target.port,
      timeout: target.timeout,
    );
    try {
      socket.add(payload.content);
      // `flush` confirma que o buffer de saída do socket foi entregue ao SO.
      await socket.flush().timeout(target.timeout);
      if (payload.cut.isNotEmpty) {
        await _delay(cutDelay); // pausa física antes da guilhotina
        socket.add(payload.cut);
        await socket.flush().timeout(target.timeout);
      }
    } finally {
      await socket.close();
    }
  }

  /// Escreve na impressora serial pela biblioteca nativa.
  ///
  /// Antes isso passava por um `SerialPort` do .NET via PowerShell, o que
  /// prendia a impressão serial ao Windows e ainda embutia os bytes em uma
  /// linha de comando. `flutter_libserialport` já é usado pela balança e pelo
  /// leitor, então a mesma via serve para a impressora nos dois sistemas.
  Future<void> _writeToSerialPrinter(
    PrinterEndpoint target,
    List<int> bytes,
  ) async {
    // A Balança Rápida roda como processo à parte (`ScaleWindowLauncher` usa
    // `Process.start`) e tem seu próprio `LocalDeviceAgent` imprimindo notas
    // de pesagem — sem trava, dois `tcsetattr` quase simultâneos na mesma
    // porta é exatamente o que produz "Argumento inválido" só na impressão
    // automática: o teste manual, feito sozinho, nunca disputa a porta com
    // ninguém. `acquireQueued` faz a espera em ordem de chegada — sem isso,
    // um retry otimista podia deixar quem pediu primeiro esperando mais que
    // quem pediu depois, só por sorte no instante de cada tentativa.
    final resource = 'printer:${target.endpoint}';
    final lock = await PeripheralLock.acquireQueued(
      resource,
      role: 'impressora',
    );
    if (lock == null) {
      final owner = await PeripheralLock.currentOwner(resource);
      throw PrinterCommunicationException(
        message: owner == null
            ? 'A porta ${target.endpoint} está ocupada por outro processo.'
            : 'A porta ${target.endpoint} está em uso por ${owner.describe()}.',
        recommendedAction:
            'Aguarde a impressão em andamento terminar e tente novamente.',
      );
    }
    try {
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
          throw _serialCommunicationError(
            target,
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
        final payload = splitCutCommand(bytes, isEscPos: target.isEscPos);
        step = 'enviar o cupom';
        _writeAllSerial(port, target, payload.content);
        _settleSerialWrite(port, target);
        if (payload.cut.isNotEmpty) {
          await _delay(cutDelay); // pausa física antes da guilhotina
          step = 'enviar o corte';
          _writeAllSerial(port, target, payload.cut);
          _settleSerialWrite(port, target);
        }
      } on SerialPortError catch (error) {
        throw _serialCommunicationError(target, step, error.message);
      } finally {
        if (port.isOpen) port.close();
        port.dispose();
      }
    } finally {
      await lock.release();
    }
  }

  /// Aguarda o driver esvaziar o buffer de saída — quando ele souber dizer.
  ///
  /// `drain` (`tcdrain`) e `bytesToWrite` (`TIOCOUTQ`) são **confirmação**, não
  /// a escrita em si. Impressoras USB que aparecem como CDC-ACM
  /// (`/dev/ttyACM*`) costumam não implementar essas duas chamadas e devolvem
  /// "Argumento inválido" — e abortar aí descartava como falha um cupom que já
  /// tinha sido entregue à porta. Por isso a falha aqui só é registrada.
  void _settleSerialWrite(SerialPort port, PrinterEndpoint target) {
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

  void _writeAllSerial(
    SerialPort port,
    PrinterEndpoint target,
    List<int> bytes,
  ) {
    if (bytes.isEmpty) return;
    final written = port.write(
      Uint8List.fromList(bytes),
      timeout: target.timeout.inMilliseconds,
    );
    if (written < bytes.length) {
      throw _serialCommunicationError(
        target,
        'enviar dados para',
        'foram aceitos apenas $written de ${bytes.length} bytes',
      );
    }
  }

  PrinterCommunicationException _serialCommunicationError(
    PrinterEndpoint target,
    String step,
    String reason,
  ) {
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

  /// Revalida os equipamentos sem bloquear a tela de vendas.
  Future<PrinterAvailability> refreshPrinterAvailability({
    bool useCachedDevices = false,
  }) async {
    if (_token == null || _restaurantId == null) {
      const status = PrinterAvailability(
        PrinterAvailabilityPhase.notConfigured,
        'Impressora desconectada',
      );
      printerAvailability.value = status;
      return status;
    }
    printerAvailability.value = const PrinterAvailability(
      PrinterAvailabilityPhase.checking,
      'Verificando impressora...',
    );
    try {
      if (!useCachedDevices || _printers.isEmpty) {
        await _syncDevicesIfNeeded();
      }
      final candidates = _printers
          .where((printer) => PrinterEndpoint.fromJson(printer).isAddressable)
          .toList();
      if (candidates.isEmpty) {
        const status = PrinterAvailability(
          PrinterAvailabilityPhase.notConfigured,
          'Impressora desconectada',
        );
        printerAvailability.value = status;
        return status;
      }
      for (final printer in candidates) {
        final target = PrinterEndpoint.fromJson(printer);
        if (await _probe(target)) {
          final status = PrinterAvailability(
            PrinterAvailabilityPhase.available,
            'Impressora disponível',
          );
          printerAvailability.value = status;
          return status;
        }
      }
    } catch (_) {
      // A indisponibilidade vira estado visual; nunca encerra a tela de venda.
    }
    const status = PrinterAvailability(
      PrinterAvailabilityPhase.unavailable,
      'Impressora desconectada',
    );
    printerAvailability.value = status;
    return status;
  }

  Future<bool> checkPrinterAvailability(
    Map<String, dynamic> printer, {
    bool publish = true,
  }) async {
    final target = PrinterEndpoint.fromJson(printer);
    final available = target.isAddressable && await _probe(target);
    if (publish) {
      printerAvailability.value = PrinterAvailability(
        available
            ? PrinterAvailabilityPhase.available
            : PrinterAvailabilityPhase.unavailable,
        available ? 'Impressora disponível' : 'Impressora desconectada',
      );
    }
    return available;
  }

  Future<bool> _probe(PrinterEndpoint target) async {
    final custom = _availabilityProbe;
    if (custom != null) return custom(target);
    try {
      switch (target.connection) {
        case PrinterConnection.serial:
          final configured = target.endpoint.trim();
          final detected = SerialPort.availablePorts.any(
            (port) => Platform.isWindows
                ? port.toLowerCase() == configured.toLowerCase()
                : port == configured,
          );
          return detected ||
              (!Platform.isWindows && await File(configured).exists());
        case PrinterConnection.network:
          final socket = await Socket.connect(
            target.host,
            target.port,
            timeout: target.timeout,
          );
          socket.destroy();
          return true;
        case PrinterConnection.spool:
          if (Platform.isWindows) {
            final safeName = target.endpoint.replaceAll("'", "''");
            final result = await Process.run('powershell.exe', [
              '-NoProfile',
              '-NonInteractive',
              '-Command',
              "Get-Printer -Name '$safeName' -ErrorAction Stop | Out-Null",
            ]).timeout(target.timeout);
            return result.exitCode == 0;
          }
          final result = await Process.run('lpstat', [
            '-p',
            target.endpoint,
          ]).timeout(target.timeout);
          return result.exitCode == 0;
      }
    } catch (_) {
      return false;
    }
  }

  /// Impressoras que este terminal já conhece, com o override local de porta
  /// aplicado.
  ///
  /// Vive em memória depois da primeira sincronização, então continua
  /// disponível com a rede fora — que é exatamente quando a comanda precisa
  /// ser montada e impressa aqui, sem esperar o backend renderizar o job.
  /// Depender de uma releitura de `/printers/` nessa hora não funciona: o
  /// cache de resposta só responde se aquela consulta exata já tiver sido
  /// feita on-line antes.
  List<Map<String, dynamic>> get knownPrinters => List.unmodifiable(_printers);

  /// Devolve as impressoras conhecidas, sincronizando se ainda não houver
  /// nenhuma. Nunca lança: sem rede e sem cache, devolve o que existir.
  Future<List<Map<String, dynamic>>> ensurePrinters() async {
    if (_printers.isEmpty) {
      try {
        await _syncDevicesIfNeeded();
      } catch (_) {
        // Segue com a lista em memória, mesmo vazia — quem chama decide o
        // que dizer ao operador.
      }
    }
    return knownPrinters;
  }

  Future<void> _syncDevicesIfNeeded() async {
    final now = DateTime.now();
    if (_lastDeviceSync != null &&
        now.difference(_lastDeviceSync!) < const Duration(seconds: 30)) {
      return;
    }
    final existing = _deviceSyncInFlight;
    if (existing != null) return existing;

    final sync =
        _list(
          '/printers/',
          query: {
            'restaurant': _restaurantId,
            'is_active': true,
            'page_size': 100,
          },
        ).then(
          // Sem override local: a impressora vale como está cadastrada.
          (printers) => _printers = printers,
        );
    _deviceSyncInFlight = sync;
    try {
      await sync;
    } finally {
      // Registra também tentativas com falha para evitar uma tempestade
      // de quatro chamadas a cada ciclo de três segundos.
      _lastDeviceSync = DateTime.now();
      if (identical(_deviceSyncInFlight, sync)) {
        _deviceSyncInFlight = null;
      }
    }
  }

  /// Último recurso quando o job não trouxe `text_content` pronto (ex.:
  /// `POST /orders/{id}/print/` não devolve o payload, só o HTML).
  ///
  /// Colapsa primeiro o espaço em branco ENTRE tags: a indentação do
  /// template Django é inconsistente (algumas linhas de tabela quebradas em
  /// várias linhas de código-fonte, outras compactas numa linha só), e sem
  /// isso o resultado dependia de acidente de formatação do HTML — uma
  /// célula ganhava quebra de linha de graça, a vizinha colava direto no
  /// valor ("SubtotalR$ 237,00"). Cada `</td>` fechado sempre vira o mesmo
  /// separador, não importa como o HTML de origem foi indentado.
  static String htmlToText(String html) => html
      .replaceAll(RegExp(r'>\s+<'), '><')
      // CSS/JS nao sao conteudo imprimivel. Sem esta remocao, o fallback de
      // jobs antigos imprimia regras como "td { padding... }" junto aos itens.
      .replaceAll(
        RegExp(r'<(style|script)\b[^>]*>[\s\S]*?</\1>', caseSensitive: false),
        '',
      )
      .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
      .replaceAll(RegExp(r'</td>', caseSensitive: false), '  ')
      .replaceAll(
        RegExp(r'</(p|div|tr|li|h[1-6])>', caseSensitive: false),
        '\n',
      )
      .replaceAll(RegExp(r'<[^>]+>'), '')
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll(RegExp(r'[ \t]+\n'), '\n')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}
