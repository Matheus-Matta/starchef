import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/formatters/value_formatters.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../data/scanner_binding_store.dart';
import '../services/serial_scanner_service.dart';

enum _ScalePhase { setup, waiting, confirming, command, completing, success }

class ScaleWorkstationPage extends StatefulWidget {
  const ScaleWorkstationPage({
    super.key,
    required this.api,
    required this.accessToken,
    required this.restaurants,
    required this.restaurantId,
    required this.products,
    required this.onRestaurantChanged,
  });

  final ApiClient api;
  final String accessToken;
  final List<Map<String, dynamic>> restaurants;
  final String? restaurantId;
  final List<Map<String, dynamic>> products;
  final Future<void> Function(String restaurantId) onRestaurantChanged;

  @override
  State<ScaleWorkstationPage> createState() => _ScaleWorkstationPageState();
}

class _ScaleWorkstationPageState extends State<ScaleWorkstationPage> {
  _ScalePhase phase = _ScalePhase.setup;
  List<Map<String, dynamic>> scales = [];
  List<Map<String, dynamic>> printers = [];
  String? scaleId;
  String? printerId;
  Map<String, dynamic>? reading;
  DateTime? stableSince;
  double lastWeight = 0;
  bool loadingScales = false;
  bool loadingPrinters = false;
  bool polling = false;
  String? errorMessage;
  Timer? pollTimer;
  Timer? ticker;
  int stableSeconds = 0;
  final commandController = TextEditingController();
  final Map<String, int> extras = {};
  final ScannerBindingStore scannerBindingStore = ScannerBindingStore();
  ScannerBinding? scannerBinding;
  SerialScannerService? scannerService;
  StreamSubscription<String>? scannerSubscription;
  bool scannerConnecting = false;
  String? scannerError;

  Map<String, dynamic>? get selectedScale => scales
      .cast<Map<String, dynamic>?>()
      .firstWhere((item) => '${item?['id']}' == scaleId, orElse: () => null);

  Map<String, dynamic>? get weighedProduct {
    final productId = '${selectedScale?['product'] ?? ''}';
    return widget.products.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == productId,
      orElse: () => null,
    );
  }

  List<Map<String, dynamic>> get unitProducts => widget.products
      .where(
        (item) =>
            item['is_active'] != false &&
            item['pricing_unit'] != 'kg' &&
            item['is_weighed'] != true,
      )
      .toList();

  double get weight =>
      _number(reading?['net_weight_kg'] ?? reading?['weight_kg']);
  double get pricePerKg => _number(weighedProduct?['current_price']);
  double get weighedTotal => weight * pricePerKg;
  int get delaySeconds =>
      (selectedScale?['auto_print_delay_seconds'] as num?)?.toInt() ?? 3;
  String? get scannerSlot {
    if (widget.restaurantId == null || scaleId == null) return null;
    return '${widget.restaurantId}:$scaleId';
  }

  @override
  void initState() {
    super.initState();
    if (widget.restaurantId != null) {
      _loadScales();
      _loadPrinters();
    }
  }

  @override
  void didUpdateWidget(covariant ScaleWorkstationPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.restaurantId != widget.restaurantId) {
      scaleId = null;
      printerId = null;
      scales = [];
      printers = [];
      _resetToSetup();
      unawaited(_detachScanner(clearBinding: true));
      _loadScales();
      _loadPrinters();
    }
  }

  @override
  void dispose() {
    pollTimer?.cancel();
    ticker?.cancel();
    unawaited(_detachScanner());
    unawaited(scannerBindingStore.close());
    commandController.dispose();
    super.dispose();
  }

  Future<void> _loadScales() async {
    if (widget.restaurantId == null) return;
    setState(() {
      loadingScales = true;
      errorMessage = null;
    });
    try {
      final response = await widget.api.get(
        '/scales/',
        query: {
          'restaurant': widget.restaurantId,
          'is_active': true,
          'page_size': 100,
        },
        accessToken: widget.accessToken,
      );
      final values = (response['results'] as List? ?? const [])
          .cast<Map<String, dynamic>>();
      if (!mounted) return;
      setState(() {
        scales = values;
        if (values.length == 1) {
          scaleId = '${values.first['id']}';
          printerId = _nullableId(values.first['printer']);
        }
      });
      if (scaleId != null) await _loadScannerBinding();
    } on ApiException catch (error) {
      if (mounted) setState(() => errorMessage = error.message);
    } finally {
      if (mounted) setState(() => loadingScales = false);
    }
  }

  Future<void> _loadPrinters() async {
    if (widget.restaurantId == null) return;
    setState(() => loadingPrinters = true);
    try {
      final response = await widget.api.get(
        '/printers/',
        query: {
          'restaurant': widget.restaurantId,
          'is_active': true,
          'page_size': 100,
        },
        accessToken: widget.accessToken,
      );
      final values = (response['results'] as List? ?? const [])
          .cast<Map<String, dynamic>>();
      if (mounted) setState(() => printers = values);
    } on ApiException catch (error) {
      if (mounted) {
        setState(() => errorMessage = 'Impressoras: ${error.message}');
      }
    } finally {
      if (mounted) setState(() => loadingPrinters = false);
    }
  }

  void _start() {
    if (scaleId == null || weighedProduct == null || printerId == null) {
      setState(() {
        errorMessage = scaleId == null
            ? 'Selecione uma balança.'
            : weighedProduct == null
            ? 'A balança precisa ter um produto por kg configurado.'
            : 'Selecione a impressora padrão desta balança.';
      });
      return;
    }
    setState(() {
      phase = _ScalePhase.waiting;
      reading = null;
      errorMessage = null;
      stableSince = null;
      stableSeconds = 0;
      lastWeight = 0;
      extras.clear();
    });
    pollTimer?.cancel();
    ticker?.cancel();
    pollTimer = Timer.periodic(
      const Duration(milliseconds: 700),
      (_) => _pollReading(),
    );
    ticker = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    _pollReading();
  }

  Future<void> _pollReading({bool showNotFound = false}) async {
    if (polling || phase != _ScalePhase.waiting || scaleId == null) return;
    polling = true;
    try {
      final result = await widget.api.get(
        '/scales/$scaleId/latest-reading/',
        accessToken: widget.accessToken,
      );
      final currentWeight = _number(
        result['net_weight_kg'] ?? result['weight_kg'],
      );
      if (!mounted || phase != _ScalePhase.waiting) return;
      final stable =
          result['is_stable'] != false &&
          currentWeight > 0 &&
          (lastWeight == 0 || (currentWeight - lastWeight).abs() <= .002);
      setState(() {
        reading = result;
        if (!stable) {
          stableSince = null;
          stableSeconds = 0;
        } else {
          stableSince ??= DateTime.now();
        }
        lastWeight = currentWeight;
        errorMessage = null;
      });
      _advanceIfStable();
    } on ApiException catch (error) {
      if ((error.statusCode != 404 || showNotFound) && mounted) {
        setState(() => errorMessage = error.message);
      }
    } finally {
      polling = false;
    }
  }

  void _tick() {
    if (!mounted || stableSince == null || phase != _ScalePhase.waiting) return;
    setState(() {
      stableSeconds = DateTime.now().difference(stableSince!).inSeconds;
    });
    _advanceIfStable();
  }

  void _advanceIfStable() {
    if (stableSince == null ||
        DateTime.now().difference(stableSince!).inSeconds < delaySeconds ||
        phase != _ScalePhase.waiting) {
      return;
    }
    pollTimer?.cancel();
    ticker?.cancel();
    setState(() => phase = _ScalePhase.confirming);
  }

  void _openCommandStep() {
    setState(() {
      phase = _ScalePhase.command;
      errorMessage = null;
      commandController.clear();
    });
  }

  Future<void> _selectScale(String? value) async {
    await _detachScanner(clearBinding: true);
    if (!mounted) return;
    final nextScale = scales.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == value,
      orElse: () => null,
    );
    setState(() {
      scaleId = value;
      printerId = _nullableId(nextScale?['printer']);
      errorMessage = null;
    });
    if (value != null) await _loadScannerBinding();
  }

  Future<void> _selectPrinter(String? value) async {
    if (scaleId == null || value == null || value == printerId) return;
    final previous = printerId;
    setState(() {
      printerId = value;
      loadingPrinters = true;
      errorMessage = null;
    });
    try {
      final updated = await widget.api.patch(
        '/scales/$scaleId/',
        body: {'printer': value},
        accessToken: widget.accessToken,
      );
      if (!mounted) return;
      setState(() {
        final index = scales.indexWhere((item) => '${item['id']}' == scaleId);
        if (index >= 0) scales[index] = updated;
        printerId = _nullableId(updated['printer']) ?? value;
      });
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          printerId = previous;
          errorMessage =
              'Não foi possível definir a impressora desta balança: '
              '${error.message}';
        });
      }
    } finally {
      if (mounted) setState(() => loadingPrinters = false);
    }
  }

  Future<void> _loadScannerBinding() async {
    final slot = scannerSlot;
    if (slot == null) return;
    await _detachScanner(clearBinding: true);
    try {
      final binding = await scannerBindingStore.read(slot);
      if (!mounted || slot != scannerSlot) return;
      setState(() {
        scannerBinding = binding;
        scannerError = null;
      });
      if (binding != null) await _connectScanner(binding);
    } catch (error) {
      if (mounted) {
        setState(() => scannerError = 'Falha ao ler o vínculo: $error');
      }
    }
  }

  Future<void> _connectScanner(ScannerBinding binding) async {
    await _detachScanner();
    if (!mounted) return;
    setState(() {
      scannerConnecting = true;
      scannerError = null;
    });
    try {
      final service = await SerialScannerService.open(binding);
      if (!mounted || binding.slot != scannerSlot) {
        await service.close();
        return;
      }
      scannerService = service;
      scannerSubscription = service.codes.listen(
        _onScannerCode,
        onError: (Object error) {
          if (mounted) {
            setState(() => scannerError = 'Leitor desconectado: $error');
          }
        },
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          scannerError =
              'Não foi possível reservar ${binding.portName}. '
              'Confira a porta ou feche a outra janela que está usando este leitor.';
        });
      }
    } finally {
      if (mounted) setState(() => scannerConnecting = false);
    }
  }

  Future<void> _detachScanner({bool clearBinding = false}) async {
    await scannerSubscription?.cancel();
    scannerSubscription = null;
    final service = scannerService;
    scannerService = null;
    if (service != null) await service.close();
    if (mounted && clearBinding) {
      setState(() {
        scannerBinding = null;
        scannerError = null;
        scannerConnecting = false;
      });
    }
  }

  void _onScannerCode(String code) {
    if (!mounted) return;
    if (phase != _ScalePhase.command) {
      SystemSound.play(SystemSoundType.alert);
      return;
    }
    commandController.text = code;
    SystemSound.play(SystemSoundType.click);
    _complete(code);
  }

  Future<void> _configureScanner() async {
    final slot = scannerSlot;
    if (slot == null) {
      setState(() => scannerError = 'Selecione uma balança primeiro.');
      return;
    }

    late final List<SerialScannerDevice> devices;
    try {
      devices = SerialScannerDevice.discover();
    } catch (error) {
      if (mounted) {
        setState(
          () => scannerError =
              'Não foi possível listar as portas seriais: $error',
        );
      }
      return;
    }
    if (!mounted) return;

    SerialScannerDevice? selected = devices
        .cast<SerialScannerDevice?>()
        .firstWhere(
          (device) => device?.portName == scannerBinding?.portName,
          orElse: () => devices.isEmpty ? null : devices.first,
        );
    var baudRate = scannerBinding?.baudRate ?? 9600;
    final choice = await showDialog<_ScannerChoice>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.barcode_reader),
              SizedBox(width: 10),
              Text('Vincular leitor desta janela'),
            ],
          ),
          content: SizedBox(
            width: 560,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Somente leitores em modo serial/USB-CDC aparecem aqui. '
                  'A porta fica reservada exclusivamente por esta janela.',
                ),
                const SizedBox(height: 18),
                if (devices.isEmpty)
                  const _ScannerEmptyState()
                else ...[
                  DropdownButtonFormField<SerialScannerDevice>(
                    initialValue: selected,
                    isExpanded: true,
                    decoration: const InputDecoration(
                      labelText: 'Leitor serial',
                      prefixIcon: Icon(Icons.usb),
                    ),
                    items: devices
                        .map(
                          (device) => DropdownMenuItem(
                            value: device,
                            child: Text(
                              device.label,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        )
                        .toList(),
                    onChanged: (value) =>
                        setDialogState(() => selected = value),
                  ),
                  const SizedBox(height: 14),
                  DropdownButtonFormField<int>(
                    initialValue: baudRate,
                    decoration: const InputDecoration(
                      labelText: 'Velocidade',
                      suffixText: 'baud',
                    ),
                    items: const [9600, 19200, 38400, 57600, 115200]
                        .map(
                          (value) => DropdownMenuItem(
                            value: value,
                            child: Text('$value'),
                          ),
                        )
                        .toList(),
                    onChanged: (value) {
                      if (value != null) {
                        setDialogState(() => baudRate = value);
                      }
                    },
                  ),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancelar'),
            ),
            FilledButton.icon(
              onPressed: selected == null
                  ? null
                  : () => Navigator.pop(
                      dialogContext,
                      _ScannerChoice(selected!, baudRate),
                    ),
              icon: const Icon(Icons.link),
              label: const Text('Vincular e testar'),
            ),
          ],
        ),
      ),
    );
    if (!mounted || choice == null || slot != scannerSlot) return;

    final binding = choice.device.bindingFor(slot, choice.baudRate);
    try {
      await scannerBindingStore.save(binding);
      if (!mounted) return;
      setState(() {
        scannerBinding = binding;
        scannerError = null;
      });
      await _connectScanner(binding);
    } catch (error) {
      if (mounted) {
        setState(
          () => scannerError =
              'Este leitor já está vinculado a outra balança ou não pôde '
              'ser salvo. Remova o vínculo anterior antes de continuar.',
        );
      }
    }
  }

  Future<void> _clearScannerBinding() async {
    final slot = scannerSlot;
    if (slot == null) return;
    await _detachScanner();
    await scannerBindingStore.clear(slot);
    if (!mounted) return;
    setState(() {
      scannerBinding = null;
      scannerError = null;
    });
  }

  Future<void> _enterManualWeight() async {
    pollTimer?.cancel();
    ticker?.cancel();
    var rawValue = '';
    String? validationMessage;
    final value = await showDialog<double>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) {
          void useWeight() {
            final parsed = double.tryParse(rawValue.replaceAll(',', '.'));
            if (parsed == null || parsed <= 0) {
              setDialogState(
                () => validationMessage = 'Informe um peso maior que zero.',
              );
              return;
            }
            if (parsed > 999) {
              setDialogState(
                () => validationMessage = 'O peso informado é muito alto.',
              );
              return;
            }
            Navigator.pop(dialogContext, parsed);
          }

          return AlertDialog(
            title: const Row(
              children: [
                Icon(Icons.touch_app_outlined),
                SizedBox(width: 10),
                Text('Peso manual'),
              ],
            ),
            content: SizedBox(
              width: 390,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 16,
                    ),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surfaceContainer,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Text(
                      '${rawValue.isEmpty ? '0,000' : rawValue} kg',
                      textAlign: TextAlign.end,
                      style: const TextStyle(
                        fontSize: 34,
                        fontWeight: FontWeight.w900,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                  ),
                  if (validationMessage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        validationMessage!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  const SizedBox(height: 14),
                  _TouchKeypad(
                    allowDecimal: true,
                    onKey: (key) {
                      setDialogState(() {
                        validationMessage = null;
                        rawValue = _nextKeypadValue(
                          rawValue,
                          key,
                          allowDecimal: true,
                          maximumLength: 7,
                        );
                      });
                    },
                  ),
                  TextButton.icon(
                    onPressed: rawValue.isEmpty
                        ? null
                        : () => setDialogState(() {
                            rawValue = '';
                            validationMessage = null;
                          }),
                    icon: const Icon(Icons.clear),
                    label: const Text('Limpar peso'),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext),
                child: const Text('Cancelar'),
              ),
              FilledButton.icon(
                onPressed: useWeight,
                icon: const Icon(Icons.check),
                label: const Text('Usar peso'),
              ),
            ],
          );
        },
      ),
    );
    if (!mounted || scaleId == null) return;
    if (value == null) {
      _start();
      return;
    }

    setState(() => polling = true);
    try {
      final result = await widget.api.post(
        '/scales/readings/',
        body: {
          'scale': scaleId,
          'weight_kg': value.toStringAsFixed(3),
          'tare_kg': '0.000',
          'is_stable': true,
          'source': 'manual',
        },
        accessToken: widget.accessToken,
      );
      pollTimer?.cancel();
      ticker?.cancel();
      if (!mounted) return;
      setState(() {
        reading = result;
        lastWeight = value;
        stableSince = DateTime.now();
        stableSeconds = delaySeconds;
        errorMessage = null;
        phase = _ScalePhase.confirming;
      });
    } on ApiException catch (error) {
      if (mounted) setState(() => errorMessage = error.message);
    } finally {
      if (mounted) setState(() => polling = false);
    }
  }

  Future<void> _complete(String rawCode) async {
    final code = rawCode.trim();
    if (phase != _ScalePhase.command || code.isEmpty || reading == null) return;
    setState(() {
      phase = _ScalePhase.completing;
      errorMessage = null;
    });
    try {
      await widget.api.post(
        '/scales/$scaleId/checkout-command/',
        body: {
          'command_code': code,
          'scale_reading': reading!['id'],
          'extras': extras.entries
              .where((entry) => entry.value > 0)
              .map((entry) => {'product': entry.key, 'quantity': entry.value})
              .toList(),
          'print': true,
        },
        accessToken: widget.accessToken,
      );
      if (!mounted) return;
      setState(() => phase = _ScalePhase.success);
      await Future<void>.delayed(const Duration(seconds: 2));
      if (mounted) _start();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        phase = _ScalePhase.command;
        errorMessage = error.message;
      });
      commandController.clear();
    }
  }

  void _handleCommandKey(String key) {
    commandController.text = _nextKeypadValue(
      commandController.text,
      key,
      maximumLength: 32,
    );
    setState(() => errorMessage = null);
  }

  void _resetToSetup() {
    pollTimer?.cancel();
    ticker?.cancel();
    if (!mounted) return;
    setState(() {
      phase = _ScalePhase.setup;
      reading = null;
      stableSince = null;
      stableSeconds = 0;
      extras.clear();
      commandController.clear();
      errorMessage = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Theme(
      data: theme.copyWith(
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            minimumSize: const Size(0, 56),
            padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 16),
          ),
        ),
        outlinedButtonTheme: OutlinedButtonThemeData(
          style: OutlinedButton.styleFrom(
            minimumSize: const Size(0, 54),
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
          ),
        ),
        textButtonTheme: TextButtonThemeData(
          style: TextButton.styleFrom(minimumSize: const Size(48, 52)),
        ),
        iconButtonTheme: IconButtonThemeData(
          style: IconButton.styleFrom(minimumSize: const Size.square(50)),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: switch (phase) {
          _ScalePhase.setup => _setup(),
          _ScalePhase.waiting => _waiting(),
          _ScalePhase.confirming => _confirming(),
          _ScalePhase.command => _command(),
          _ScalePhase.completing => _completing(),
          _ScalePhase.success => _success(),
        },
      ),
    );
  }

  Widget _setup() => Center(
    child: SizedBox(
      width: 620,
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.scale_outlined, size: 58),
              const SizedBox(height: 14),
              const Text(
                'Estação de balança',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 24),
              DropdownButtonFormField<String>(
                initialValue: widget.restaurantId,
                decoration: const InputDecoration(labelText: 'Restaurante'),
                items: widget.restaurants
                    .map(
                      (item) => DropdownMenuItem(
                        value: '${item['id']}',
                        child: Text('${item['trade_name'] ?? item['name']}'),
                      ),
                    )
                    .toList(),
                onChanged: (value) {
                  if (value != null && value != widget.restaurantId) {
                    widget.onRestaurantChanged(value);
                  }
                },
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                key: ValueKey('scale-$scaleId-${scales.length}'),
                initialValue: scaleId,
                decoration: InputDecoration(
                  labelText: 'Balança',
                  suffixIcon: loadingScales
                      ? const Padding(
                          padding: EdgeInsets.all(12),
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : null,
                ),
                items: scales
                    .map(
                      (item) => DropdownMenuItem(
                        value: '${item['id']}',
                        child: Text('${item['name']} · ${item['port'] ?? ''}'),
                      ),
                    )
                    .toList(),
                onChanged: (value) => unawaited(_selectScale(value)),
              ),
              if (scaleId != null) ...[
                const SizedBox(height: 14),
                _scannerBindingCard(),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  key: ValueKey(
                    'printer-$scaleId-$printerId-${printers.length}',
                  ),
                  initialValue:
                      printers.any((item) => '${item['id']}' == printerId)
                      ? printerId
                      : null,
                  isExpanded: true,
                  decoration: InputDecoration(
                    labelText: 'Impressora padrão da balança',
                    prefixIcon: const Icon(Icons.print_outlined),
                    helperText:
                        'O ticket de pesagem sempre será enviado para esta impressora.',
                    suffixIcon: loadingPrinters
                        ? const Padding(
                            padding: EdgeInsets.all(12),
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : null,
                  ),
                  items: printers
                      .map(
                        (item) => DropdownMenuItem(
                          value: '${item['id']}',
                          child: Text(
                            '${item['name']} · ${_printerTransport(item)}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: loadingPrinters
                      ? null
                      : (value) => unawaited(_selectPrinter(value)),
                ),
              ],
              if (weighedProduct != null) ...[
                const SizedBox(height: 12),
                Text(
                  'Produto: ${weighedProduct!['name']} · ${ValueFormatters.money(pricePerKg)}/kg',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ],
              if (errorMessage != null) _errorBox(),
              const SizedBox(height: 22),
              FilledButton.icon(
                onPressed: loadingScales ? null : _start,
                icon: const Icon(Icons.play_arrow),
                label: const Text('Iniciar estação'),
              ),
            ],
          ),
        ),
      ),
    ),
  );

  Widget _scannerBindingCard() {
    final connected = scannerService != null && scannerError == null;
    final colorScheme = Theme.of(context).colorScheme;
    final statusColor = scannerError != null
        ? colorScheme.error
        : connected
        ? Colors.green.shade700
        : colorScheme.onSurfaceVariant;
    final statusLabel = scannerConnecting
        ? 'Reservando porta...'
        : scannerError != null
        ? scannerError!
        : connected
        ? 'Leitor reservado exclusivamente por esta janela'
        : scannerBinding == null
        ? 'Nenhum leitor serial vinculado'
        : 'Leitor configurado, mas desconectado';

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: scannerError != null
              ? colorScheme.error.withValues(alpha: .45)
              : colorScheme.outlineVariant,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: .12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: scannerConnecting
                ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(
                    connected ? Icons.usb_rounded : Icons.usb_off_outlined,
                    color: statusColor,
                  ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  scannerBinding?.hardwareIdentity ?? 'Leitor da comanda',
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 3),
                Text(
                  statusLabel,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: statusColor,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          if (scannerBinding != null)
            IconButton(
              tooltip: 'Remover vínculo',
              onPressed: scannerConnecting ? null : _clearScannerBinding,
              icon: const Icon(Icons.link_off),
            ),
          OutlinedButton(
            onPressed: scannerConnecting ? null : _configureScanner,
            child: Text(scannerBinding == null ? 'Vincular' : 'Alterar'),
          ),
        ],
      ),
    );
  }

  Widget _waiting() => _stageCard(
    icon: Icons.monitor_weight_outlined,
    title: 'Aguardando pesagem',
    subtitle: 'Coloque o produto na balança e aguarde a estabilização.',
    child: Column(
      children: [
        Text(
          weight.toStringAsFixed(3),
          style: const TextStyle(fontSize: 82, fontWeight: FontWeight.w900),
        ),
        const Text('kg', style: TextStyle(fontSize: 24)),
        const SizedBox(height: 18),
        LinearProgressIndicator(
          value: stableSince == null
              ? null
              : (stableSeconds / delaySeconds).clamp(0, 1),
        ),
        const SizedBox(height: 8),
        Text(
          stableSince == null
              ? 'Esperando leitura estável...'
              : 'Confirmando estabilidade por $delaySeconds segundos...',
        ),
        if (errorMessage != null) _errorBox(),
        const SizedBox(height: 18),
        FilledButton.icon(
          onPressed: polling ? null : () => _pollReading(showNotFound: true),
          icon: polling
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Icon(Icons.scale_outlined),
          label: const Text('Buscar kg na balança'),
        ),
        const SizedBox(height: 4),
        TextButton.icon(
          onPressed: polling ? null : _enterManualWeight,
          style: TextButton.styleFrom(
            visualDensity: VisualDensity.compact,
            textStyle: const TextStyle(fontSize: 12),
          ),
          icon: const Icon(Icons.keyboard_alt_outlined, size: 16),
          label: const Text('Digitar peso manualmente'),
        ),
      ],
    ),
  );

  Widget _confirming() => Row(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Expanded(
        flex: 5,
        child: _stageCard(
          icon: Icons.check_circle_outline,
          title: 'Confirme com o cliente',
          subtitle: '${weighedProduct?['name'] ?? 'Produto por kg'}',
          child: Column(
            children: [
              Text(
                '${weight.toStringAsFixed(3)} kg',
                style: const TextStyle(
                  fontSize: 42,
                  fontWeight: FontWeight.w900,
                ),
              ),
              Text('${ValueFormatters.money(pricePerKg)}/kg'),
              const Divider(height: 36),
              Text(
                ValueFormatters.money(weighedTotal),
                style: Theme.of(
                  context,
                ).textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _openCommandStep,
                icon: const Icon(Icons.verified_outlined),
                label: const Text('Cliente confirmou · Ler comanda'),
              ),
            ],
          ),
        ),
      ),
      const SizedBox(width: 20),
      Expanded(
        flex: 4,
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(22),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Adicionar bebidas ou extras',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Itens adicionados somente após a confirmação do peso.',
                ),
                const SizedBox(height: 16),
                Expanded(
                  child: ListView.separated(
                    itemCount: unitProducts.length,
                    separatorBuilder: (_, _) => const Divider(height: 1),
                    itemBuilder: (_, index) {
                      final product = unitProducts[index];
                      final id = '${product['id']}';
                      final quantity = extras[id] ?? 0;
                      return ListTile(
                        title: Text('${product['name']}'),
                        subtitle: Text(
                          ValueFormatters.money(product['current_price']),
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              onPressed: quantity == 0
                                  ? null
                                  : () => setState(
                                      () => extras[id] = quantity - 1,
                                    ),
                              icon: const Icon(Icons.remove_circle_outline),
                            ),
                            SizedBox(
                              width: 28,
                              child: Text(
                                '$quantity',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                            ),
                            IconButton(
                              onPressed: quantity >= 99
                                  ? null
                                  : () => setState(
                                      () => extras[id] = quantity + 1,
                                    ),
                              icon: const Icon(Icons.add_circle_outline),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ],
  );

  Widget _command() => _stageCard(
    icon: Icons.qr_code_scanner,
    title: 'Leia a comanda',
    subtitle: scannerService != null
        ? 'Aproxime a comanda do leitor exclusivo desta janela.'
        : 'Use o teclado touch para informar o número da comanda.',
    child: Column(
      children: [
        if (scannerBinding != null)
          Container(
            margin: const EdgeInsets.only(bottom: 14),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
            decoration: BoxDecoration(
              color: scannerService != null
                  ? Colors.green.withValues(alpha: .1)
                  : Theme.of(context).colorScheme.errorContainer,
              borderRadius: BorderRadius.circular(30),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  scannerService != null ? Icons.usb_rounded : Icons.usb_off,
                  size: 18,
                ),
                const SizedBox(width: 7),
                Flexible(
                  child: Text(
                    scannerService != null
                        ? scannerBinding!.hardwareIdentity
                        : 'Leitor indisponível · use o teclado touch',
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
              ],
            ),
          ),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 430),
          child: TextField(
            controller: commandController,
            readOnly: true,
            showCursor: false,
            enableInteractiveSelection: false,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w900),
            decoration: const InputDecoration(
              labelText: 'Código da comanda',
              prefixIcon: Icon(Icons.badge_outlined),
            ),
          ),
        ),
        if (errorMessage != null) _errorBox(),
        const SizedBox(height: 14),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 430),
          child: _TouchKeypad(onKey: _handleCommandKey),
        ),
        const SizedBox(height: 16),
        ConstrainedBox(
          constraints: const BoxConstraints(minWidth: 300, maxWidth: 430),
          child: FilledButton.icon(
            onPressed: commandController.text.trim().isEmpty
                ? null
                : () => _complete(commandController.text),
            icon: const Icon(Icons.check),
            label: const Text('Finalizar na comanda'),
          ),
        ),
      ],
    ),
  );

  Widget _completing() => _stageCard(
    icon: Icons.sync,
    title: 'Finalizando pedido',
    subtitle: 'Não retire a comanda até a confirmação.',
    child: const Center(child: CircularProgressIndicator()),
  );

  Widget _success() => _stageCard(
    icon: Icons.task_alt,
    title: 'Pedido lançado com sucesso',
    subtitle: 'Preparando a estação para o próximo cliente...',
    child: const Center(
      child: Icon(Icons.check_circle, size: 92, color: Colors.green),
    ),
  );

  Widget _stageCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required Widget child,
  }) => LayoutBuilder(
    builder: (context, constraints) => Center(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 760,
          maxHeight: constraints.maxHeight,
        ),
        child: Card(
          child: Padding(
            padding: EdgeInsets.all(constraints.maxHeight < 620 ? 18 : 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(icon, size: constraints.maxHeight < 620 ? 36 : 48),
                SizedBox(height: constraints.maxHeight < 620 ? 5 : 10),
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                  ),
                ),
                const SizedBox(height: 5),
                Text(subtitle, textAlign: TextAlign.center),
                SizedBox(height: constraints.maxHeight < 620 ? 12 : 26),
                Expanded(child: SingleChildScrollView(child: child)),
                if (phase != _ScalePhase.completing &&
                    phase != _ScalePhase.success)
                  TextButton.icon(
                    onPressed: _resetToSetup,
                    icon: const Icon(Icons.settings_outlined),
                    label: const Text('Trocar restaurante ou balança'),
                  ),
              ],
            ),
          ),
        ),
      ),
    ),
  );

  Widget _errorBox() => Padding(
    padding: const EdgeInsets.only(top: 14),
    child: Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        errorMessage!,
        textAlign: TextAlign.center,
        style: TextStyle(
          color: Theme.of(context).colorScheme.onErrorContainer,
          fontWeight: FontWeight.w700,
        ),
      ),
    ),
  );

  double _number(dynamic value) =>
      value is num ? value.toDouble() : double.tryParse('$value') ?? 0;
}

class _ScannerChoice {
  const _ScannerChoice(this.device, this.baudRate);

  final SerialScannerDevice device;
  final int baudRate;
}

class _ScannerEmptyState extends StatelessWidget {
  const _ScannerEmptyState();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(18),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.surfaceContainer,
      borderRadius: BorderRadius.circular(14),
    ),
    child: const Column(
      children: [
        Icon(Icons.usb_off_outlined, size: 38),
        SizedBox(height: 8),
        Text(
          'Nenhuma porta serial disponível',
          style: TextStyle(fontWeight: FontWeight.w900),
        ),
        SizedBox(height: 4),
        Text(
          'Conecte o leitor configurado como USB-CDC/COM e abra esta tela novamente.',
          textAlign: TextAlign.center,
        ),
      ],
    ),
  );
}

class _TouchKeypad extends StatelessWidget {
  const _TouchKeypad({required this.onKey, this.allowDecimal = false});

  final ValueChanged<String> onKey;
  final bool allowDecimal;

  @override
  Widget build(BuildContext context) {
    final keys = [
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
      allowDecimal ? ',' : 'C',
      '0',
      'backspace',
    ];
    return SizedBox(
      height: 256,
      child: GridView.builder(
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          mainAxisExtent: 58,
          mainAxisSpacing: 8,
          crossAxisSpacing: 8,
        ),
        itemCount: keys.length,
        itemBuilder: (context, index) {
          final keyValue = keys[index];
          final destructive = keyValue == 'C' || keyValue == 'backspace';
          return keyValue == 'backspace'
              ? OutlinedButton(
                  onPressed: () => onKey(keyValue),
                  child: const Icon(Icons.backspace_outlined),
                )
              : destructive
              ? OutlinedButton(
                  onPressed: () => onKey(keyValue),
                  child: Text(
                    keyValue,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                )
              : FilledButton.tonal(
                  onPressed: () => onKey(keyValue),
                  child: Text(
                    keyValue,
                    style: const TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                );
        },
      ),
    );
  }
}

String _nextKeypadValue(
  String current,
  String key, {
  bool allowDecimal = false,
  int maximumLength = 32,
}) {
  if (key == 'C') return '';
  if (key == 'backspace') {
    return current.isEmpty ? current : current.substring(0, current.length - 1);
  }
  if (key == ',') {
    if (!allowDecimal || current.contains(',') || current.contains('.')) {
      return current;
    }
    return current.isEmpty ? '0,' : '$current,';
  }
  if (current.length >= maximumLength) return current;
  if (allowDecimal && current.contains(',')) {
    final decimals = current.length - current.indexOf(',') - 1;
    if (decimals >= 3) return current;
  }
  return '$current$key';
}

String? _nullableId(dynamic value) {
  final normalized = value?.toString().trim() ?? '';
  return normalized.isEmpty || normalized == 'null' ? null : normalized;
}

String _printerTransport(Map<String, dynamic> printer) {
  final connection = '${printer['connection_type'] ?? 'windows'}';
  if (connection == 'network') {
    final host = '${printer['host'] ?? ''}'.trim();
    final port = printer['port'] ?? 9100;
    return host.isEmpty ? 'Rede' : '$host:$port';
  }
  if (connection == 'serial') {
    final endpoint = '${printer['endpoint'] ?? ''}'.trim();
    return endpoint.isEmpty ? 'Serial' : endpoint;
  }
  final endpoint = '${printer['endpoint'] ?? ''}'.trim();
  return endpoint.isEmpty ? 'Windows / USB' : endpoint;
}
