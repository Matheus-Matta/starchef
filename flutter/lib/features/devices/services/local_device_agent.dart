import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/realtime_client.dart';
import '../domain/printer_endpoint.dart';
import 'print_template_cache.dart';

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
/// `/ws/realtime/` (todo `TenantModel` ganha isso de graça — ver
/// `apps/realtime/signals.py`). O agente assina esse evento e só consulta
/// `/print-jobs/` quando um deles chega, mais uma verificação pontual ao
/// conectar/reconectar o WS, para cobrir o que foi perdido enquanto a conexão
/// estava caída. Modelos de impressão seguem a mesma regra: sem timer,
/// sincroniza no início e a cada reconexão.
class LocalDeviceAgent {
  LocalDeviceAgent({required this.api});

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
    final qrBytes = isEscPos && qrValue != null ? escPosQrCodeBytes(qrValue) : null;
    final printableContent = barcodeBytes == null
        ? textWithBarcodeFallback(content, barcodeValue)
        : content;
    return <int>[
      ...utf8.encode(printableContent),
      ...?barcodeBytes,
      ...?qrBytes,
      if (isEscPos) ...const [10, 10, 10, 29, 86, 0],
    ];
  }

  final ApiClient api;
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

  void start({required String token, required String restaurantId}) {
    if (_realtime != null && _token == token && _restaurantId == restaurantId) {
      return;
    }
    _token = token;
    _restaurantId = restaurantId;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _backoffUntil = null;
    _stopRealtime();
    if (!Platform.isWindows) return;
    final realtime = RealtimeClient(
      urlBuilder: () => api.realtimeSocketUrl(_token!),
    );
    _realtime = realtime;
    // Ao (re)conectar, uma verificação pontual cobre o que pode ter mudado
    // enquanto a conexão estava caída — nunca um timer recorrente.
    _connectedSubscription = realtime.onConnected.listen((_) => _onConnected());
    _eventSubscription = realtime.events
        .where((event) => isPrintJobEvent(event, _restaurantId))
        .listen((_) => _onPrintJobEvent());
    realtime.start();
  }

  void stop() {
    _stopRealtime();
    _token = null;
    _restaurantId = null;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _backoffUntil = null;
    _deviceSyncInFlight = null;
    _printers = const [];
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

  Future<void> _onConnected() => _guarded(() {
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
    await _syncDevicesIfNeeded();
    final availablePrinters = <String, Map<String, dynamic>>{
      for (final printer in _printers)
        if (PrinterEndpoint.fromJson(printer).isAddressable)
          '${printer['id']}': printer,
    };

    for (final status in ['pending', 'rendered']) {
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
    final target = PrinterEndpoint.fromJson(printer);
    final missing = target.missingConfiguration;
    if (missing != null) throw StateError(missing);

    if (target.connection == PrinterConnection.spool) {
      // O spool recebe texto puro (Out-Printer/lp não renderizam imagem) — o
      // QR não sai escaneável por essa via, mesma limitação que o Code128 já
      // tem hoje aqui; o texto ainda traz a chave de acesso pra consulta manual.
      await printText(
        target.endpoint,
        textWithBarcodeFallback(content, barcodeValue),
      );
      return;
    }

    final printBytes = rawTransportBytes(
      content,
      isEscPos: target.isEscPos,
      barcodeValue: barcodeValue,
      qrValue: qrValue,
    );
    if (target.connection == PrinterConnection.network) {
      final socket = await Socket.connect(
        target.host,
        target.port,
        timeout: target.timeout,
      );
      try {
        socket.add(printBytes);
        await socket.flush();
      } finally {
        await socket.close();
      }
      return;
    }
    await _writeToSerialPrinter(target, printBytes);
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
      if (!port.openWrite()) {
        throw StateError(
          'Não foi possível abrir ${target.endpoint}: '
          '${SerialPort.lastError?.message ?? 'porta ocupada ou inexistente'}.',
        );
      }
      port.config = SerialPortConfig()
        ..baudRate = target.baudRate
        ..bits = 8
        ..parity = SerialPortParity.none
        ..stopBits = 1;
      final written = port.write(
        Uint8List.fromList(bytes),
        timeout: target.timeout.inMilliseconds,
      );
      if (written < bytes.length) {
        throw StateError(
          'A impressora aceitou apenas $written de ${bytes.length} bytes '
          'em ${target.endpoint}.',
        );
      }
      port.drain();
    } on SerialPortError catch (error) {
      throw StateError(
        'Falha na porta ${target.endpoint}: ${error.message}',
      );
    } finally {
      if (port.isOpen) port.close();
      port.dispose();
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

    final sync = _list(
      '/printers/',
      query: {
        'restaurant': _restaurantId,
        'is_active': true,
        'page_size': 100,
      },
    ).then((printers) => _printers = printers);
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
