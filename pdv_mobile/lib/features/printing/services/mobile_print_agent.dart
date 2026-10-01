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
  final Map<String, int> _falhas = {};
  final Set<String> _awaitingConfirmation = {};

  Timer? _timer;
  String? _restaurantId;
  bool _runningCycle = false;
  bool _rerunRequested = false;
  DateTime? _printersLoadedAt;
  List<MobilePrinter> _printers = const [];
  PrintAgentState _state = PrintAgentState.stopped;
  bool _permissionGranted = true;
  String? _lastError;
  DateTime? _lastSyncAt;
  int _printedCount = 0;
  bool _disposed = false;

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
    _timer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => unawaited(runNow()),
    );
    unawaited(_refreshPermission());
    try {
      _awaitingConfirmation.addAll(await confirmations.load());
    } catch (_) {
      // Arquivo de confirmações ilegível não pode desligar a impressão.
    }
    await runNow();
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _restaurantId = null;
    _state = PrintAgentState.stopped;
    _printers = const [];
    _printersLoadedAt = null;
    _retryAfter.clear();
    _falhas.clear();
    _rerunRequested = false;
    notifyListeners();
  }

  Future<void> runNow() async {
    final restaurant = _restaurantId;
    if (restaurant == null) return;
    if (_runningCycle) {
      _rerunRequested = true;
      return;
    }
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
      if (_rerunRequested && _restaurantId != null) {
        _rerunRequested = false;
        unawaited(runNow());
      }
    }
  }

  Future<void> requestPermissionAgain() async {
    await _refreshPermission();
    await runNow();
  }

  /// A permissão NUNCA segura a impressão.
  ///
  /// Socket TCP para a impressora da loja não depende dela; e o pedido ao
  /// Android pode não voltar (tela recriada no meio do diálogo) ou voltar com
  /// erro. Esperar por ele era o que deixava o agente parado em "Solicitando
  /// permissão" para sempre, mesmo depois de a pessoa ter autorizado.
  Future<void> _refreshPermission() async {
    try {
      _permissionGranted = await permission.request().timeout(
        const Duration(seconds: 30),
        onTimeout: () => _permissionGranted,
      );
    } catch (_) {
      // Sem resposta do Android: segue imprimindo e deixa o botão da tela de
      // impressão para pedir de novo.
    }
    if (!_disposed) notifyListeners();
  }

  Future<void> openSystemSettings() => permission.openSettings();

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
