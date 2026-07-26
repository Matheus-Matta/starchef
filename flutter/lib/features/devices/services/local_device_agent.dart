import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../../../core/network/api_client.dart';
import 'print_template_cache.dart';

class LocalDeviceAgent {
  LocalDeviceAgent({required this.api}) {
    _instanceIdFuture = _loadInstanceId();
  }

  final ApiClient api;
  late final Future<String> _instanceIdFuture;
  Timer? _timer;
  bool _running = false;
  String? _token;
  String? _restaurantId;
  DateTime? _lastTemplateSync;
  DateTime? _lastDeviceSync;
  List<Map<String, dynamic>> _printers = const [];
  List<Map<String, dynamic>> _scales = const [];
  final Map<String, String> _lastScaleValue = {};
  final Map<String, DateTime> _scaleStableSince = {};
  final Set<String> _armedScales = {};

  void start({required String token, required String restaurantId}) {
    _token = token;
    _restaurantId = restaurantId;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _timer?.cancel();
    if (!Platform.isWindows) return;
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _tick());
    unawaited(_tick());
  }

  void stop() {
    final token = _token;
    if (token != null) {
      unawaited(_releaseClaimedScales(token));
    }
    _timer?.cancel();
    _timer = null;
    _token = null;
    _restaurantId = null;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _printers = const [];
    _scales = const [];
    _lastScaleValue.clear();
    _scaleStableSince.clear();
    _armedScales.clear();
  }

  Future<void> _tick() async {
    if (_running || _token == null || _restaurantId == null) return;
    _running = true;
    try {
      final shouldSyncTemplates =
          _lastTemplateSync == null ||
          DateTime.now().difference(_lastTemplateSync!) >
              const Duration(minutes: 5);
      await Future.wait([
        _processPrintJobs(),
        _readScales(),
        if (shouldSyncTemplates) _syncTemplates(),
      ]);
    } catch (_) {
      // O agente é tolerante a falhas: a próxima rodada tenta novamente.
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
    final availablePrinters = <String, Map<String, dynamic>>{};
    for (final printer in _printers) {
      final settings = printer['settings'] as Map<String, dynamic>? ?? const {};
      final endpoint = '${printer['endpoint'] ?? ''}'.trim();
      final host = '${printer['host'] ?? settings['host'] ?? ''}'.trim();
      final connectionType =
          '${settings['connection_type'] ?? printer['connection_type'] ?? 'windows'}';
      final hasConnection = connectionType == 'network'
          ? host.isNotEmpty
          : endpoint.isNotEmpty;
      if (!hasConnection) continue;
      availablePrinters['${printer['id']}'] = printer;
    }

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
          await printForPrinter(printer, text);
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
    final readyText = '${job['payload']?['text_content'] ?? ''}'.trim();
    final text = readyText.isNotEmpty
        ? readyText
        : _htmlToText('${job['html'] ?? job['html_content'] ?? ''}');
    if (text.isEmpty) {
      throw StateError('O trabalho não possui conteúdo para impressão.');
    }
    try {
      await printForPrinter(printer, text);
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

  Future<void> printText(String printerName, String content) async {
    final temp = File(
      '${Directory.systemTemp.path}${Platform.pathSeparator}starchef-${DateTime.now().microsecondsSinceEpoch}.txt',
    );
    await temp.writeAsString(content, encoding: utf8, flush: true);
    final safePath = temp.path.replaceAll("'", "''");
    final safePrinter = printerName.replaceAll("'", "''");
    try {
      final result = await Process.run('powershell.exe', [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        "Get-Content -LiteralPath '$safePath' -Raw | Out-Printer -Name '$safePrinter'",
      ]).timeout(const Duration(seconds: 20));
      if (result.exitCode != 0) {
        throw ProcessException(
          'powershell.exe',
          const [],
          '${result.stderr}',
          result.exitCode,
        );
      }
    } finally {
      if (await temp.exists()) await temp.delete();
    }
  }

  Future<void> printForPrinter(
    Map<String, dynamic> printer,
    String content,
  ) async {
    final settings = printer['settings'] as Map<String, dynamic>? ?? const {};
    final connectionType =
        '${settings['connection_type'] ?? printer['connection_type'] ?? 'windows'}';
    final timeout = Duration(
      seconds:
          int.tryParse(
            '${printer['timeout_seconds'] ?? settings['timeout_seconds'] ?? 10}',
          ) ??
          10,
    );
    if (connectionType == 'network') {
      final host = '${printer['host'] ?? settings['host'] ?? ''}'.trim();
      final port =
          int.tryParse('${printer['port'] ?? settings['port'] ?? 9100}') ??
          9100;
      if (host.isEmpty) {
        throw StateError('O endereço IP da impressora não foi configurado.');
      }
      final socket = await Socket.connect(host, port, timeout: timeout);
      try {
        socket.add(utf8.encode(content));
        if ('${printer['driver_type']}' == 'escpos') {
          socket.add(const [10, 10, 10, 29, 86, 0]);
        }
        await socket.flush();
      } finally {
        await socket.close();
      }
      return;
    }
    if (connectionType == 'serial') {
      final port = '${printer['endpoint'] ?? ''}'.trim();
      if (port.isEmpty) {
        throw StateError('A porta serial da impressora não foi configurada.');
      }
      final baudRate = int.tryParse('${settings['baudrate'] ?? 9600}') ?? 9600;
      final safePort = port.replaceAll("'", "''");
      final base64 = base64Encode(utf8.encode(content));
      final command =
          "\$p = [System.IO.Ports.SerialPort]::new('$safePort', $baudRate); "
          "\$p.WriteTimeout = ${timeout.inMilliseconds}; "
          "try { \$p.Open(); "
          "\$b = [Convert]::FromBase64String('$base64'); "
          "\$p.Write(\$b, 0, \$b.Length) "
          "} finally { if (\$p.IsOpen) { \$p.Close() }; \$p.Dispose() }";
      final result = await Process.run('powershell.exe', [
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        command,
      ]).timeout(timeout);
      if (result.exitCode != 0) {
        throw ProcessException(
          'powershell.exe',
          const [],
          '${result.stderr}',
          result.exitCode,
        );
      }
      return;
    }
    final endpoint = '${printer['endpoint'] ?? ''}'.trim();
    if (endpoint.isEmpty) {
      throw StateError('A impressora do Windows não foi configurada.');
    }
    await printText(endpoint, content);
  }

  Future<void> _readScales() async {
    await _syncDevicesIfNeeded();
    for (final scale in _scales) {
      if (scale['auto_print'] != true) continue;
      final port = '${scale['port'] ?? ''}'.trim();
      if (port.isEmpty) continue;
      try {
        final scaleId = '${scale['id']}';
        if (!await _claimScale(scaleId)) continue;
        final settings = scale['settings'] as Map<String, dynamic>? ?? const {};
        final baudRate =
            int.tryParse('${settings['baudrate'] ?? 9600}') ?? 9600;
        final output = await _readSerialLine(port, baudRate);
        final weight = _parseWeight(output);
        if (weight == null) continue;
        final zeroThreshold =
            double.tryParse('${settings['zero_threshold_kg'] ?? 0.005}') ??
            0.005;
        if (weight <= zeroThreshold) {
          _armedScales.add(scaleId);
          _lastScaleValue.remove(scaleId);
          _scaleStableSince.remove(scaleId);
          continue;
        }

        final signature = weight.toStringAsFixed(3);
        if (_lastScaleValue[scaleId] != signature) {
          _lastScaleValue[scaleId] = signature;
          _scaleStableSince[scaleId] = DateTime.now();
          continue;
        }
        final stableSince = _scaleStableSince[scaleId] ?? DateTime.now();
        final delaySeconds =
            int.tryParse('${scale['auto_print_delay_seconds'] ?? 3}') ?? 3;
        if (DateTime.now().difference(stableSince) <
            Duration(seconds: delaySeconds)) {
          continue;
        }

        // A balanca precisa ter passado por zero antes de cada disparo. Isso
        // impede duplicidade inclusive quando o aplicativo e reiniciado com
        // um prato ainda apoiado.
        if (!_armedScales.contains(scaleId)) continue;
        _armedScales.remove(scaleId);
        await api.post(
          '/scales/readings/',
          body: {
            'scale': scale['id'],
            'agent_instance_id': await _instanceIdFuture,
            'weight_kg': signature,
            'tare_kg': '0.000',
            'is_stable': true,
            'source': 'agent',
          },
          accessToken: _token,
        );
        _scaleStableSince.remove(scaleId);
      } catch (_) {
        // Uma balança desconectada não interrompe impressoras ou outras balanças.
      }
    }
  }

  Future<void> _syncDevicesIfNeeded() async {
    final now = DateTime.now();
    if (_lastDeviceSync != null &&
        now.difference(_lastDeviceSync!) < const Duration(seconds: 30)) {
      return;
    }
    final devices = await Future.wait([
      _list(
        '/printers/',
        query: {
          'restaurant': _restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      ),
      _list(
        '/scales/',
        query: {
          'restaurant': _restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      ),
    ]);
    _printers = devices[0];
    _scales = devices[1];
    _lastDeviceSync = now;
  }

  Future<bool> _claimScale(String scaleId) async {
    try {
      final response = await api.post(
        '/scales/$scaleId/claim-agent/',
        body: {'instance_id': await _instanceIdFuture},
        accessToken: _token,
      );
      return response['claimed'] == true;
    } catch (_) {
      // Conflito significa que outro PDV ainda possui a balanca. Falhas de
      // rede tambem impedem a leitura, evitando operar sem a trava central.
      return false;
    }
  }

  Future<void> _releaseClaimedScales(String token) async {
    final instanceId = await _instanceIdFuture;
    final scaleIds = <String>{
      ..._lastScaleValue.keys,
      ..._armedScales,
      ..._scaleStableSince.keys,
    };
    for (final scaleId in scaleIds) {
      try {
        await api.post(
          '/scales/$scaleId/release-agent/',
          body: {'instance_id': instanceId},
          accessToken: token,
        );
      } catch (_) {
        // A concessao expira sozinha caso o encerramento esteja sem rede.
      }
    }
  }

  Future<String> _loadInstanceId() async {
    final localAppData = Platform.environment['LOCALAPPDATA']?.trim();
    final base = localAppData == null || localAppData.isEmpty
        ? Directory.systemTemp
        : Directory(localAppData);
    final directory = Directory(
      '${base.path}${Platform.pathSeparator}StarChef',
    );
    final file = File(
      '${directory.path}${Platform.pathSeparator}device_agent_id.txt',
    );
    try {
      if (await file.exists()) {
        final existing = (await file.readAsString()).trim();
        if (existing.isNotEmpty) return existing;
      }
      await directory.create(recursive: true);
      final generated =
          '${Platform.localHostname}-${DateTime.now().microsecondsSinceEpoch}';
      await file.writeAsString(generated, flush: true);
      return generated;
    } catch (_) {
      return '${Platform.localHostname}-${DateTime.now().microsecondsSinceEpoch}';
    }
  }

  Future<String> _readSerialLine(String port, int baudRate) async {
    final safePort = port.replaceAll("'", "''");
    final command =
        "\$p = [System.IO.Ports.SerialPort]::new('$safePort', $baudRate); "
        "\$p.ReadTimeout = 900; "
        "try { \$p.Open(); \$p.ReadLine() } finally { if (\$p.IsOpen) { \$p.Close() }; \$p.Dispose() }";
    final result = await Process.run('powershell.exe', [
      '-NoProfile',
      '-NonInteractive',
      '-Command',
      command,
    ]).timeout(const Duration(seconds: 3));
    if (result.exitCode != 0) {
      throw ProcessException(
        'powershell.exe',
        const [],
        '${result.stderr}',
        result.exitCode,
      );
    }
    return '${result.stdout}'.trim();
  }

  double? _parseWeight(String raw) {
    final matches = RegExp(r'-?\d+(?:[.,]\d+)?').allMatches(raw).toList();
    if (matches.isEmpty) return null;
    final value = matches.last.group(0)!.replaceAll(',', '.');
    var weight = double.tryParse(value);
    if (weight == null) return null;
    if (!value.contains('.') && weight > 100) weight /= 1000;
    return weight;
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
