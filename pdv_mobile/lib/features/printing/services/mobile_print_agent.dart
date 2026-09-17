import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../domain/mobile_print_job_policy.dart';
import '../domain/mobile_printer.dart';
import 'escpos_mobile_encoder.dart';
import 'nearby_printer_permission.dart';
import 'network_printer_writer.dart';
import 'print_confirmation_store.dart';

part 'mobile_print_agent_support.dart';

enum PrintAgentState { stopped, requestingPermission, syncing, ready, error }

class MobilePrintAgent extends ChangeNotifier {
  MobilePrintAgent({
    required this.api,
    this.permission = const NearbyPrinterPermission(),
    this.writer = const NetworkPrinterWriter(),
    this.encoder = const EscPosMobileEncoder(),
    PrintConfirmationStorage? confirmations,
  }) : confirmations = confirmations ?? FilePrintConfirmationStore();

  final ApiClient api;
  final NearbyPrinterPermission permission;
  final NetworkPrinterWriter writer;
  final EscPosMobileEncoder encoder;
  final PrintConfirmationStorage confirmations;
  final Map<String, DateTime> _retryAfter = {};
  final Set<String> _awaitingConfirmation = {};

  Timer? _timer;
  String? _restaurantId;
  bool _runningCycle = false;
  DateTime? _printersLoadedAt;
  List<MobilePrinter> _printers = const [];
  PrintAgentState _state = PrintAgentState.stopped;
  bool _permissionGranted = true;
  String? _lastError;
  DateTime? _lastSyncAt;
  int _printedCount = 0;

  PrintAgentState get state => _state;
  bool get permissionGranted => _permissionGranted;
  String? get lastError => _lastError;
  DateTime? get lastSyncAt => _lastSyncAt;
  int get printedCount => _printedCount;
  List<MobilePrinter> get printers => List.unmodifiable(_printers);
  int get supportedPrinters =>
      _printers.where((item) => item.acceptsAutomaticJobs).length;

  Future<void> start(String restaurantId) async {
    if (_restaurantId == restaurantId && _timer != null) return;
    stop();
    _restaurantId = restaurantId;
    _state = PrintAgentState.requestingPermission;
    notifyListeners();
    _permissionGranted = await permission.request();
    _awaitingConfirmation.addAll(await confirmations.load());
    await runNow();
    _timer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => unawaited(runNow()),
    );
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _restaurantId = null;
    _state = PrintAgentState.stopped;
    _printers = const [];
    _printersLoadedAt = null;
    _retryAfter.clear();
    notifyListeners();
  }

  Future<void> runNow() async {
    final restaurant = _restaurantId;
    if (_runningCycle || restaurant == null) return;
    _runningCycle = true;
    _state = PrintAgentState.syncing;
    notifyListeners();
    try {
      _lastError = null;
      await _confirmPrintedJobs();
      await _loadPrintersIfNeeded(restaurant);
      await _processJobs(restaurant);
      _lastSyncAt = DateTime.now();
      _state = PrintAgentState.ready;
    } on ApiException catch (error) {
      _lastError = error.message;
      _state = PrintAgentState.error;
    } catch (error) {
      _lastError = '$error';
      _state = PrintAgentState.error;
    } finally {
      _runningCycle = false;
      notifyListeners();
    }
  }

  Future<void> requestPermissionAgain() async {
    _permissionGranted = await permission.request();
    notifyListeners();
    await runNow();
  }

  Future<void> openSystemSettings() => permission.openSettings();

  Future<void> _processJobs(String restaurant) async {
    final available = {
      for (final printer in _printers)
        if (printer.acceptsAutomaticJobs) printer.id: printer,
    };
    if (available.isEmpty) return;
    for (final status in ['pending', 'rendered']) {
      final page = await api.get(
        '/print-jobs/',
        query: {
          'restaurant': restaurant,
          'status': status,
          'ordering': 'created_at',
          'page_size': 100,
        },
      );
      for (final job in _rows(page)) {
        if (!MobilePrintJobPolicy.shouldAutomaticallyPrint(job)) continue;
        final jobId = '${job['id'] ?? ''}';
        final printer = available['${job['printer'] ?? ''}'];
        final retryAt = _retryAfter[jobId];
        if (jobId.isEmpty || printer == null) continue;
        if (_awaitingConfirmation.contains(jobId)) continue;
        if (retryAt != null && retryAt.isAfter(DateTime.now())) continue;
        if (!await _claim(jobId)) continue;
        await _printJob(jobId, job, printer);
      }
    }
  }

  Future<bool> _claim(String jobId) async {
    try {
      await api.post('/print-jobs/$jobId/claim/');
      return true;
    } on ApiException catch (error) {
      if (error.statusCode == 409) return false;
      rethrow;
    }
  }

  Future<void> _printJob(
    String jobId,
    Map<String, dynamic> job,
    MobilePrinter printer,
  ) async {
    final payload = job['payload'] is Map
        ? Map<String, dynamic>.from(job['payload'] as Map)
        : const <String, dynamic>{};
    final text = '${payload['text_content'] ?? ''}'.trimRight();
    if (text.isEmpty) {
      await api.post(
        '/print-jobs/$jobId/mark-failed/',
        body: {'error': 'Trabalho sem text_content.'},
      );
      return;
    }
    final barcode = payload['barcode'] is Map
        ? '${(payload['barcode'] as Map)['value'] ?? ''}'
        : '';
    try {
      await writer.write(
        printer,
        encoder.encode(text: text, barcode: barcode, escPos: printer.isEscPos),
      );
      _printedCount += 1;
      _retryAfter.remove(jobId);
      _awaitingConfirmation.add(jobId);
      await confirmations.add(jobId);
      await _confirmPrintedJob(jobId);
    } catch (error) {
      if (_awaitingConfirmation.contains(jobId)) {
        _lastError = 'O papel saiu, mas a confirmação ficou pendente: $error';
        return;
      }
      _retryAfter[jobId] = DateTime.now().add(const Duration(seconds: 30));
      await api.post('/print-jobs/$jobId/release/');
      _lastError = '$error';
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
