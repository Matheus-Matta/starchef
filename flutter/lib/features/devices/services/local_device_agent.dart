import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/realtime_client.dart';
import '../../../core/storage/local_preferences.dart';
import '../domain/printer_endpoint.dart';
import 'print_template_cache.dart';

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
/// (`claim-agent`), a consulta periódica de peso pela API e a disputa entre
/// este agente e a janela pela mesma COM.
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
    this.cutDelay = const Duration(milliseconds: 650),
  }) : _availabilityProbe = availabilityProbe,
       _networkWriter = networkWriter,
       _delay = delay ?? Future<void>.delayed;

  static const List<int> escPosCutBytes = [0x1d, 0x56, 0x00];

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
    final contentBytes = isEscPos
        ? _readableReceiptBytes(printableContent)
        : utf8.encode(printableContent);
    return <int>[
      ...contentBytes,
      ...?barcodeBytes,
      ...?qrBytes,
      // A distância entre a cabeça de impressão e a guilhotina varia por
      // modelo; 3 linhas não bastava em impressoras genéricas e cortava
      // texto/código de barras que ainda não tinha saído.
      if (isEscPos) ...const [10, 10, 10, 10, 10, 10, ...escPosCutBytes],
    ];
  }

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
      result.addAll(_encodeCp850(line));
      result.add(0x0a);
      if (normalized.isNotEmpty) firstTextLine = false;
    }
    result.addAll([0x1b, 0x21, 0x00]);
    return result;
  }

  /// Codifica o texto na pagina PC850 usada pelas termicas vendidas no Brasil.
  /// Caracteres fora da pagina viram equivalentes seguros, evitando que os
  /// bytes UTF-8 aparecam impressos como "Ã", "Â" ou trechos de estilo.
  static List<int> _encodeCp850(String value) {
    const extended = <int, int>{
      0x00c7: 0x80,
      0x00fc: 0x81,
      0x00e9: 0x82,
      0x00e2: 0x83,
      0x00e4: 0x84,
      0x00e0: 0x85,
      0x00e7: 0x87,
      0x00ea: 0x88,
      0x00eb: 0x89,
      0x00e8: 0x8a,
      0x00ef: 0x8b,
      0x00ee: 0x8c,
      0x00ec: 0x8d,
      0x00c4: 0x8e,
      0x00c9: 0x90,
      0x00f4: 0x93,
      0x00f6: 0x94,
      0x00f2: 0x95,
      0x00fb: 0x96,
      0x00f9: 0x97,
      0x00d6: 0x99,
      0x00dc: 0x9a,
      0x00e1: 0xa0,
      0x00ed: 0xa1,
      0x00f3: 0xa2,
      0x00fa: 0xa3,
      0x00e3: 0xc6,
      0x00c3: 0xc7,
      0x00f5: 0xe4,
      0x00d5: 0xe5,
    };
    const replacements = <int, int>{
      0x2013: 0x2d,
      0x2014: 0x2d,
      0x2018: 0x27,
      0x2019: 0x27,
      0x201c: 0x22,
      0x201d: 0x22,
      0x00b7: 0x2d,
      0x00d7: 0x78,
    };
    return value.runes.map((rune) {
      if (rune <= 0x7f) return rune;
      return extended[rune] ?? replacements[rune] ?? 0x3f;
    }).toList();
  }

  final ApiClient api;
  final LocalPreferences? preferences;
  final Future<bool> Function(PrinterEndpoint target)? _availabilityProbe;
  final Future<void> Function(PrinterEndpoint target, List<int> bytes)?
  _networkWriter;
  final Future<void> Function(Duration duration) _delay;
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
    printerAvailability.value = const PrinterAvailability(
      PrinterAvailabilityPhase.checking,
      'Verificando impressora...',
    );
    unawaited(refreshPrinterAvailability());
    _availabilityTimer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => unawaited(refreshPrinterAvailability(useCachedDevices: true)),
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
        if (printer == null) continue;
        final payload = job['payload'] as Map<String, dynamic>? ?? const {};
        if (payload['manual_only'] == true) continue;
        final isAutomaticWeighTicket = '${job['job_type']}' == 'weigh_ticket';
        if (printer['auto_print'] != true && !isAutomaticWeighTicket) {
          continue;
        }
        try {
          final readyText = '${payload['text_content'] ?? ''}'.trim();
          final text = readyText.isNotEmpty
              ? readyText
              : _htmlToText('${job['html_content'] ?? ''}');
          if (text.trim().isEmpty) {
            throw const FormatException('O trabalho não possui conteúdo.');
          }
          await printForPrinter(
            printer,
            text,
            barcodeValue: code128ValueFromPayload(payload),
            qrValue: qrValueFromPayload(payload),
          );
          await api.post(
            '/print-jobs/${job['id']}/mark-printed/',
            body: const {},
            accessToken: _token,
          );
        } catch (error) {
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
      _scheduledPrintTimer = Timer(
        wait.isNegative
            ? const Duration(milliseconds: 100)
            : wait + const Duration(milliseconds: 150),
        () => unawaited(_guarded(_processPrintJobs)),
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
        : _htmlToText('${job['html'] ?? job['html_content'] ?? ''}');
    if (text.isEmpty) {
      throw StateError('O trabalho não possui conteúdo para impressão.');
    }
    try {
      await printForPrinter(
        printer,
        text,
        barcodeValue: code128ValueFromPayload(payload),
        qrValue: qrValueFromPayload(payload),
      );
      await api.post(
        '/print-jobs/$jobId/mark-printed/',
        body: const {},
        accessToken: token,
      );
    } catch (error) {
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
    await temp.writeAsString(content, encoding: utf8, flush: true);
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
    // O cadastro no backend guarda um endpoint só (ex.: /dev/starchef-printer),
    // mas o nome real do dispositivo varia por terminal — sem aplicar o
    // override local aqui, um trabalho de impressão de verdade ignorava a
    // porta configurada nas Preferências deste terminal e falhava mesmo
    // quando o teste de conexão (que já passava por outra tela) funcionava.
    final resolvedPrinter =
        preferences?.applySerialPort(printer, kind: 'printer') ?? printer;
    final target = PrinterEndpoint.fromJson(resolvedPrinter);
    final missing = target.missingConfiguration;
    if (missing != null) {
      printerAvailability.value = const PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        'Impressora desconectada',
      );
      throw PrinterCommunicationException(
        message: 'Falha ao comunicar com a impressora. $missing',
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
        throw const PrinterCommunicationException(
          message:
              'Falha ao comunicar com a impressora: dispositivo não encontrado.',
          recommendedAction:
              'Confira o cabo, a energia e a porta configurada. O PDV continuará funcionando normalmente.',
        );
      }

      if (target.connection == PrinterConnection.spool) {
        // O spool recebe texto puro (Out-Printer/lp não renderizam imagem).
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
        if (target.connection == PrinterConnection.network) {
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
    } on PrinterCommunicationException {
      printerAvailability.value = const PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        'Impressora desconectada',
      );
      rethrow;
    } catch (error) {
      printerAvailability.value = const PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        'Impressora desconectada',
      );
      throw PrinterCommunicationException(
        message: 'Falha ao comunicar com a impressora: $error',
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
    final port = SerialPort(target.endpoint);
    try {
      // Alguns drivers COM virtuais do Windows rejeitam um handle aberto
      // somente para escrita com ERROR_INVALID_HANDLE, embora aceitem o modo
      // leitura/escrita usado pelas APIs e ferramentas nativas do sistema.
      if (!port.openReadWrite()) {
        throw _serialCommunicationError(
          target,
          SerialPort.lastError?.message ?? 'porta ocupada ou inexistente',
        );
      }
      port.config = SerialPortConfig()
        ..baudRate = target.baudRate
        ..bits = 8
        ..parity = SerialPortParity.none
        ..stopBits = 1;
      final payload = splitCutCommand(bytes, isEscPos: target.isEscPos);
      _writeAllSerial(port, target, payload.content);
      // `drain` aguarda a transmissão física e `bytesToWrite` confirma que o
      // buffer do driver realmente chegou a zero antes da guilhotina.
      port.drain();
      if (port.bytesToWrite != 0) {
        throw _serialCommunicationError(
          target,
          '${port.bytesToWrite} bytes ainda estavam no buffer de saída',
        );
      }
      if (payload.cut.isNotEmpty) {
        await _delay(cutDelay); // pausa física antes da guilhotina
        _writeAllSerial(port, target, payload.cut);
        port.drain();
        if (port.bytesToWrite != 0) {
          throw _serialCommunicationError(
            target,
            '${port.bytesToWrite} bytes do corte ficaram no buffer de saída',
          );
        }
      }
    } on SerialPortError catch (error) {
      throw _serialCommunicationError(target, error.message);
    } finally {
      if (port.isOpen) port.close();
      port.dispose();
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
        'foram enviados apenas $written de ${bytes.length} bytes',
      );
    }
  }

  PrinterCommunicationException _serialCommunicationError(
    PrinterEndpoint target,
    String reason,
  ) {
    final available = SerialPort.availablePorts;
    final detected = available.isEmpty ? 'nenhuma' : available.join(', ');
    return PrinterCommunicationException(
      message:
          'Falha ao comunicar pela porta ${target.endpoint} '
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
          (printers) => _printers = printers
              .map(
                (printer) =>
                    preferences?.applySerialPort(printer, kind: 'printer') ??
                    printer,
              )
              .toList(),
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

  String _htmlToText(String html) => html
      // CSS/JS nao sao conteudo imprimivel. Sem esta remocao, o fallback de
      // jobs antigos imprimia regras como "td { padding... }" junto aos itens.
      .replaceAll(
        RegExp(r'<(style|script)\b[^>]*>[\s\S]*?</\1>', caseSensitive: false),
        '',
      )
      .replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n')
      .replaceAll(
        RegExp(r'</(p|div|tr|li|h[1-6])>', caseSensitive: false),
        '\n',
      )
      .replaceAll(RegExp(r'<[^>]+>'), '')
      .replaceAll('&nbsp;', ' ')
      .replaceAll('&amp;', '&')
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}
