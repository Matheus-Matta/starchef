import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/errors/app_error_host.dart';
import '../../../core/errors/app_error.dart';
import '../../../core/formatters/value_formatters.dart';
import '../../../core/widgets/touch_keypad.dart';
import '../../../core/hardware/scale/scale_protocol.dart';
import '../../../core/hardware/scale/scale_sample.dart';
import '../../../core/hardware/scale/serial_scale_reader.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/storage/local_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../../core/widgets/app_dialog.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../devices/domain/printer_endpoint.dart';
import '../../home/presentation/product_catalog_panel.dart';
import '../../orders/presentation/product_config_dialog.dart';
import '../data/scanner_binding_store.dart';
import '../domain/hands_free_machine.dart';
import '../services/serial_scanner_service.dart';

class ScaleWorkstationPage extends StatefulWidget {
  const ScaleWorkstationPage({
    super.key,
    required this.api,
    required this.accessToken,
    required this.restaurants,
    required this.restaurantId,
    required this.products,
    required this.onRestaurantChanged,
    required this.preferences,
    this.onRunningChanged,
  });

  final ApiClient api;
  final String accessToken;
  final List<Map<String, dynamic>> restaurants;
  final String? restaurantId;
  final List<Map<String, dynamic>> products;
  final Future<void> Function(String restaurantId) onRestaurantChanged;
  final LocalPreferences preferences;
  final ValueChanged<bool>? onRunningChanged;

  @override
  State<ScaleWorkstationPage> createState() => _ScaleWorkstationPageState();
}

class _ScaleWorkstationPageState extends State<ScaleWorkstationPage> {
  List<Map<String, dynamic>> scales = [];
  List<Map<String, dynamic>> printers = [];
  String? scaleId;
  String? printerId;
  bool loadingScales = false;
  bool loadingPrinters = false;
  bool started = false;
  String? errorMessage;

  /// Leitor serial desta janela. `null` significa que nenhuma porta foi
  /// configurada no cadastro da balança.
  SerialScaleReader? reader;
  StreamSubscription<ScaleSample>? sampleSubscription;
  StreamSubscription<ScaleLinkStatus>? linkSubscription;
  ScaleLinkStatus linkStatus = const ScaleLinkStatus(
    state: ScaleLinkState.disconnected,
    message: 'Balança não configurada nesta estação.',
  );

  late HandsFreeMachine machine = _buildMachine();
  Timer? clock;

  final commandController = TextEditingController();
  final commandFocusNode = FocusNode(debugLabel: 'command-input');
  final ScannerBindingStore scannerBindingStore = ScannerBindingStore();
  ScannerBinding? scannerBinding;
  SerialScannerService? scannerService;
  StreamSubscription<String>? scannerSubscription;
  bool scannerConnecting = false;
  String? scannerError;

  /// Trabalho de impressão do último cupom, disponível para reimpressão.
  String? lastPrintJobId;
  bool reprinting = false;

  /// Busca e filtro da grade de extras, no mesmo formato do PDV.
  String extrasSearch = '';
  String? extrasCategory;

  /// Variação, adicionais e observação escolhidos por extra, na mesma
  /// pergunta que o PDV padrão faz. `machine.extras` só guarda a
  /// quantidade — o resto fica aqui porque é detalhe de interface, não do
  /// fluxo hands-free.
  final Map<String, ProductConfigResult> extraConfigs = {};

  bool requestingWeight = false;

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

  /// Categorias derivadas dos próprios produtos.
  ///
  /// Evita mais uma chamada só para montar o filtro, e continua funcionando
  /// com o terminal offline, já que o cardápio vem do cache.
  List<Map<String, dynamic>> get extraCategories {
    final byId = <String, String>{};
    for (final product in unitProducts) {
      final id = '${product['category'] ?? ''}';
      final name = '${product['category_name'] ?? ''}'.trim();
      if (id.isNotEmpty && name.isNotEmpty) byId[id] = name;
    }
    final entries = byId.entries.toList()
      ..sort((a, b) => a.value.toLowerCase().compareTo(b.value.toLowerCase()));
    return [
      for (final entry in entries) {'id': entry.key, 'name': entry.value},
    ];
  }

  /// Extras após a busca e o filtro de categoria.
  List<Map<String, dynamic>> get visibleExtras {
    final term = extrasSearch.trim().toLowerCase();
    return unitProducts.where((product) {
      if (extrasCategory != null &&
          '${product['category']}' != extrasCategory) {
        return false;
      }
      if (term.isEmpty) return true;
      return [
        '${product['name'] ?? ''}',
        '${product['internal_code'] ?? ''}',
        '${product['category_name'] ?? ''}',
      ].any((field) => field.toLowerCase().contains(term));
    }).toList();
  }

  double get pricePerKg =>
      ValueFormatters.number(weighedProduct?['current_price']);

  /// Segundos de estabilidade exigidos, vindos do cadastro da balança.
  int get settleSeconds =>
      (selectedScale?['auto_print_delay_seconds'] as num?)?.toInt() ?? 3;

  String? get scannerSlot {
    if (widget.restaurantId == null || scaleId == null) return null;
    return '${widget.restaurantId}:$scaleId';
  }

  String get configuredPort => '${selectedScale?['port'] ?? ''}'.trim();

  HandsFreeMachine _buildMachine() =>
      HandsFreeMachine(commandTimeout: widget.preferences.commandTimeout);

  @override
  void initState() {
    super.initState();
    machine.addListener(_onMachineChanged);
    HardwareKeyboard.instance.addHandler(_handleFallbackKeyboard);
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
      unawaited(_stopStation());
      unawaited(_detachScanner(clearBinding: true));
      _loadScales();
      _loadPrinters();
    }
  }

  @override
  void dispose() {
    clock?.cancel();
    HardwareKeyboard.instance.removeHandler(_handleFallbackKeyboard);
    machine.removeListener(_onMachineChanged);
    machine.dispose();
    unawaited(sampleSubscription?.cancel());
    unawaited(linkSubscription?.cancel());
    unawaited(reader?.dispose());
    unawaited(_detachScanner());
    unawaited(scannerBindingStore.close());
    commandController.dispose();
    commandFocusNode.dispose();
    super.dispose();
  }

  void _onMachineChanged() {
    if (!mounted) return;
    setState(() {});
    if (_acceptsCommandInput) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _acceptsCommandInput) commandFocusNode.requestFocus();
      });
    }
  }

  bool get _acceptsCommandInput => switch (machine.state) {
    HandsFreeState.waitingCommand ||
    HandsFreeState.commandOverdue ||
    HandsFreeState.failed => true,
    _ => false,
  };

  bool _handleFallbackKeyboard(KeyEvent event) {
    if (event is! KeyDownEvent ||
        !_acceptsCommandInput ||
        commandFocusNode.hasFocus) {
      return false;
    }

    final keyboard = HardwareKeyboard.instance;
    final key = event.logicalKey;
    if (keyboard.isControlPressed && key == LogicalKeyboardKey.keyV) {
      unawaited(_pasteCommandFromClipboard());
      return true;
    }
    if (key == LogicalKeyboardKey.enter ||
        key == LogicalKeyboardKey.numpadEnter) {
      _submitCommandInput();
      return true;
    }
    if (key == LogicalKeyboardKey.backspace) {
      final value = commandController.text;
      if (value.isNotEmpty) {
        _replaceCommandText(value.substring(0, value.length - 1));
      }
      return true;
    }
    if (keyboard.isControlPressed ||
        keyboard.isAltPressed ||
        keyboard.isMetaPressed) {
      return false;
    }
    final character = event.character;
    if (character == null ||
        character.isEmpty ||
        character.runes.any((rune) => rune < 0x20 || rune == 0x7f)) {
      return false;
    }
    _replaceCommandText('${commandController.text}$character');
    return true;
  }

  Future<void> _pasteCommandFromClipboard() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    if (!mounted || !_acceptsCommandInput) return;
    final pasted = data?.text?.replaceAll(RegExp(r'[\r\n\t]'), '').trim();
    if (pasted == null || pasted.isEmpty) return;
    _replaceCommandText('${commandController.text}$pasted');
  }

  void _replaceCommandText(String value) {
    final normalized = value.length <= 32 ? value : value.substring(0, 32);
    commandController.value = TextEditingValue(
      text: normalized,
      selection: TextSelection.collapsed(offset: normalized.length),
    );
    if (mounted) setState(() {});
  }

  void _submitCommandInput() {
    final code = commandController.text.trim();
    if (code.isEmpty) return;
    _runEffects(machine.onCommandRead(code));
  }

  // ---------------------------------------------------------------- catálogo

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
          .cast<Map<String, dynamic>>()
          .map(
            (item) => widget.preferences.applySerialPort(item, kind: 'scale'),
          )
          .toList();
      if (!mounted) return;
      setState(() {
        scales = values;
        if (values.length == 1) {
          scaleId = '${values.first['id']}';
          printerId = ValueFormatters.nullableId(values.first['printer']);
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
          .cast<Map<String, dynamic>>()
          .map(
            (item) => widget.preferences.applySerialPort(item, kind: 'printer'),
          )
          .toList();
      if (mounted) setState(() => printers = values);
    } on ApiException catch (error) {
      if (mounted) {
        setState(() => errorMessage = 'Impressoras: ${error.message}');
      }
    } finally {
      if (mounted) setState(() => loadingPrinters = false);
    }
  }

  Future<void> _selectScale(String? value) async {
    await _stopStation();
    await _detachScanner(clearBinding: true);
    if (!mounted) return;
    final nextScale = scales.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == value,
      orElse: () => null,
    );
    setState(() {
      scaleId = value;
      printerId = ValueFormatters.nullableId(nextScale?['printer']);
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
        printerId = ValueFormatters.nullableId(updated['printer']) ?? value;
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

  // ------------------------------------------------------- ciclo da estação

  Future<void> _startStation() async {
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
      errorMessage = null;
      started = true;
    });
    widget.onRunningChanged?.call(true);
    await _attachReader();
    machine.start();
    clock?.cancel();
    clock = Timer.periodic(const Duration(seconds: 1), (_) => _onClockTick());
  }

  Future<void> _stopStation() async {
    clock?.cancel();
    clock = null;
    await sampleSubscription?.cancel();
    sampleSubscription = null;
    await linkSubscription?.cancel();
    linkSubscription = null;
    final current = reader;
    reader = null;
    await current?.dispose();
    machine.stop();
    extraConfigs.clear();
    if (!mounted) return;
    setState(() {
      started = false;
      linkStatus = const ScaleLinkStatus(
        state: ScaleLinkState.disconnected,
        message: 'Estação parada.',
      );
    });
    widget.onRunningChanged?.call(false);
  }

  /// Abre a porta serial desta janela e passa a receber o peso localmente.
  ///
  /// Não há consulta periódica à API para obter peso: o equipamento transmite
  /// e este processo decodifica. A rede só participa na hora de lançar o
  /// pedido.
  Future<void> _attachReader() async {
    await sampleSubscription?.cancel();
    await linkSubscription?.cancel();
    await reader?.dispose();
    sampleSubscription = null;
    linkSubscription = null;
    reader = null;

    final port = configuredPort;
    if (port.isEmpty) {
      setState(() {
        linkStatus = const ScaleLinkStatus(
          state: ScaleLinkState.disconnected,
          message:
              'A balança não tem porta serial cadastrada. Informe a COM e o '
              'baud rate no cadastro para ler o peso automaticamente.',
        );
      });
      return;
    }

    final settings =
        selectedScale?['settings'] as Map<String, dynamic>? ?? const {};
    final baudRate = int.tryParse('${settings['baudrate'] ?? 9600}') ?? 9600;
    final next = SerialScaleReader.serial(
      portName: port,
      baudRate: baudRate,
      protocol: ScaleProtocol.forId('${settings['protocol'] ?? ''}'),
      stabilityToleranceKg: widget.preferences.stabilityToleranceKg,
      settleDuration: Duration(seconds: settleSeconds),
      zeroThresholdKg:
          double.tryParse('${settings['zero_threshold_kg'] ?? 0.005}') ?? 0.005,
      ownerDetail: '${selectedScale?['name'] ?? 'balança'}',
    );
    reader = next;
    sampleSubscription = next.samples.listen(_onSample);
    linkSubscription = next.statusChanges.listen((status) {
      if (mounted) setState(() => linkStatus = status);
    });
    await next.start();
  }

  /// Pede uma pesagem ao equipamento e explica o resultado ao operador.
  ///
  /// Só a solicitação é feita aqui: o peso, se vier, entra pelo mesmo caminho
  /// de qualquer leitura e continua passando pela regra de estabilidade. O
  /// botão não confirma peso nenhum por conta própria.
  Future<void> _requestWeight() async {
    final current = reader;
    if (current == null) {
      setState(() {
        errorMessage =
            'Esta balança não tem porta serial cadastrada. Informe a COM e o '
            'baud rate no cadastro, ou use o peso manual.';
      });
      return;
    }
    setState(() {
      requestingWeight = true;
      errorMessage = null;
    });
    try {
      final result = await current.requestWeight();
      if (!mounted) return;
      final message = switch (result) {
        ScaleWeightRequest.sent => null,
        ScaleWeightRequest.writeNotSupported =>
          'A porta ${current.portName} abriu somente para leitura, então não '
              'dá para pedir o peso. Se o visor mostra o peso mas nada chega '
              'aqui, configure a balança em transmissão contínua ou use o '
              'peso manual.',
        ScaleWeightRequest.notConnected =>
          'Não foi possível abrir ${current.portName}. Confira o cabo e se '
              'outra janela está usando a porta.',
        ScaleWeightRequest.unavailable =>
          'A estação precisa estar em operação para falar com a balança.',
      };
      setState(() => errorMessage = message);
      if (result == ScaleWeightRequest.sent) {
        // A resposta chega pelo fluxo; um retorno vazio depois de alguns
        // segundos aparece no cartão de diagnóstico como "sem resposta".
        showAppToast(context, 'Peso solicitado à balança.');
      }
    } finally {
      if (mounted) setState(() => requestingWeight = false);
    }
  }

  void _onSample(ScaleSample sample) {
    if (!mounted || !started) return;
    _runEffects(machine.onSample(sample, pricePerKg: pricePerKg));
  }

  void _onClockTick() {
    if (!mounted) return;
    _runEffects(machine.tick(DateTime.now()));
    // O contador regressivo do alerta precisa redesenhar a cada segundo.
    setState(() {});
  }

  void _runEffects(List<HandsFreeEffect> effects) {
    for (final effect in effects) {
      switch (effect) {
        case HandsFreeEffect.alertSound:
          if (widget.preferences.audibleAlerts) {
            SystemSound.play(SystemSoundType.alert);
          }
        case HandsFreeEffect.successSound:
          if (widget.preferences.audibleAlerts) {
            SystemSound.play(SystemSoundType.click);
          }
        case HandsFreeEffect.createOrder:
          unawaited(_createOrder());
        case HandsFreeEffect.operationCancelled:
          commandController.clear();
          extraConfigs.clear();
          reader?.resetStability();
          AppLogger.instance.info('scale_operation_cancelled');
      }
    }
  }

  // ------------------------------------------------------- criação do pedido

  /// Lança o pedido na comanda e imprime o cupom.
  ///
  /// A leitura é registrada no servidor no mesmo instante do lançamento, e não
  /// a cada pesagem: assim uma operação cancelada não deixa leituras órfãs.
  Future<void> _createOrder() async {
    final item = machine.weighedItem;
    final code = machine.commandCode;
    if (item == null || code == null || scaleId == null) return;
    try {
      final reading = await widget.api.post(
        '/scales/readings/',
        body: {
          'scale': scaleId,
          'weight_kg': item.weightKg.toStringAsFixed(3),
          'tare_kg': '0.000',
          'is_stable': true,
          'source': 'agent',
        },
        accessToken: widget.accessToken,
      );
      final result = await widget.api.post(
        '/scales/$scaleId/checkout-command/',
        body: {
          'command_code': code,
          'scale_reading': reading['id'],
          'extras': machine.extras.entries
              .where((entry) => entry.value > 0)
              .map((entry) {
                final config = extraConfigs[entry.key];
                return {
                  'product': entry.key,
                  'quantity': entry.value,
                  if (config?.variationId != null)
                    'variations': [config!.variationId],
                  if (config?.addonIds.isNotEmpty == true)
                    'addons': config!.addonIds,
                  if (config?.customerNote.isNotEmpty == true)
                    'customer_note': config!.customerNote,
                };
              })
              .toList(),
          'print': widget.preferences.autoPrint,
        },
        accessToken: widget.accessToken,
      );
      if (!mounted) return;
      AppLogger.instance.info(
        'scale_checkout_ok',
        data: {'command': code, 'weight_kg': item.weightKg},
      );
      final printJob = result['print_job'];
      setState(() {
        lastPrintJobId = printJob is Map
            ? '${printJob['id'] ?? ''}'.trim().isEmpty
                  ? null
                  : '${printJob['id']}'
            : null;
      });
      if (widget.preferences.autoPrint && lastPrintJobId != null) {
        await _monitorPrintJob(lastPrintJobId!);
        if (!mounted) return;
      }
      machine.onOrderCreated();
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted || !started) return;
      reader?.resetStability();
      // Mesmo momento em que a máquina zera `_extras` (readyForNext ->
      // _resetOperation): sem isso, o próximo cliente herdaria a
      // configuração de adicionais do anterior.
      extraConfigs.clear();
      commandController.clear();
      machine.readyForNext();
    } on ApiException catch (error) {
      if (!mounted) return;
      AppLogger.instance.warning(
        'scale_checkout_failed',
        data: {'command': code, 'message': error.message},
      );
      // A venda não é descartada: o item pesado continua na máquina e o
      // operador pode reler a comanda depois de resolver a recusa.
      _runEffects(machine.onOrderFailed(error.message));
      ErrorCenterScope.read(context).reportApi(
        error,
        title: 'A comanda não pôde ser fechada',
        recommendedAction:
            'Feche este alerta, confira a comanda e leia novamente. '
            'A pesagem foi preservada.',
      );
      commandController.clear();
    } catch (error, stackTrace) {
      if (!mounted) return;
      _runEffects(
        machine.onOrderFailed('Falha inesperada ao lançar o pedido.'),
      );
      ErrorCenterScope.read(context).reportUnexpected(
        error,
        title: 'A comanda não pôde ser fechada',
        stackTrace: stackTrace,
      );
    }
  }

  /// Aguarda a confirmação do agente de impressão. Criar o PrintJob não
  /// significa que a impressora recebeu o cupom; sem acompanhar o estado, uma
  /// falha de rede ficava invisível e a tela dizia apenas “pedido concluído”.
  Future<void> _monitorPrintJob(String jobId) async {
    for (var attempt = 0; attempt < 16; attempt++) {
      if (attempt > 0) {
        await Future<void>.delayed(const Duration(milliseconds: 500));
      }
      try {
        final job = await widget.api.get(
          '/print-jobs/$jobId/',
          accessToken: widget.accessToken,
        );
        if (!mounted) return;
        final status = '${job['status'] ?? ''}';
        if (status == 'printed') {
          showAppToast(context, 'Pedido concluído e comanda impressa.');
          return;
        }
        if (status == 'failed') {
          final detail = '${job['error_message'] ?? ''}'.trim();
          ErrorCenterScope.read(context).report(
            AppError(
              title: 'Pedido concluído, mas a impressão falhou',
              message: detail.isEmpty
                  ? 'A impressora não confirmou o recebimento da comanda.'
                  : detail,
              origin: AppErrorOrigin.peripheral,
              recommendedAction:
                  'Confira o IP, a porta e a energia da impressora e use Reimprimir.',
              dedupeKey: 'scale-print-$jobId',
            ),
          );
          return;
        }
      } on ApiException catch (error) {
        AppLogger.instance.warning(
          'scale_print_status_failed',
          data: {'print_job': jobId, 'message': error.message},
        );
      }
    }
    if (!mounted) return;
    ErrorCenterScope.read(context).report(
      AppError(
        title: 'Pedido concluído; impressão aguardando confirmação',
        message:
            'O trabalho foi criado, mas o agente de impressão ainda não confirmou a comanda.',
        origin: AppErrorOrigin.peripheral,
        severity: AppErrorSeverity.warning,
        recommendedAction:
            'Confira se o PDV principal está aberto e use Reimprimir se necessário.',
        dedupeKey: 'scale-print-$jobId',
      ),
    );
  }

  /// Reimprime o último cupom sem criar outro pedido.
  ///
  /// Reenfileira o mesmo trabalho de impressão em vez de gerar um novo a
  /// partir do pedido: assim o cupom sai idêntico, com o layout da nota de
  /// pesagem e o Code 128 da comanda, e nenhum item é lançado de novo.
  Future<void> _reprintLastTicket() async {
    final jobId = lastPrintJobId;
    if (jobId == null || reprinting) return;
    setState(() => reprinting = true);
    try {
      await widget.api.post(
        '/print-jobs/$jobId/requeue/',
        body: const {},
        accessToken: widget.accessToken,
      );
      if (!mounted) return;
      await _monitorPrintJob(jobId);
      if (!mounted) return;
      AppLogger.instance.info('scale_reprint', data: {'print_job': jobId});
    } on ApiException catch (error) {
      if (!mounted) return;
      ErrorCenterScope.read(context).reportApi(
        error,
        title: 'Não foi possível reimprimir',
        recommendedAction:
            'O pedido continua lançado. Verifique a impressora e tente de novo.',
      );
    } finally {
      if (mounted) setState(() => reprinting = false);
    }
  }

  // -------------------------------------------------------------- scanner

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
    } catch (_) {
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
    commandController.text = code;
    _runEffects(machine.onCommandRead(code));
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
        builder: (context, setDialogState) => AppDialog(
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
    } catch (_) {
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

  // --------------------------------------------------------- peso manual

  Future<void> _enterManualWeight() async {
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

          return AppDialog(
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
                      borderRadius: AppTheme.radius,
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
                  TouchKeypad(
                    allowDecimal: true,
                    onKey: (key) {
                      setDialogState(() {
                        validationMessage = null;
                        rawValue = nextKeypadValue(
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
    if (!mounted || value == null || scaleId == null) return;

    // Um peso digitado entra na máquina como uma amostra já estável, seguindo
    // exatamente o mesmo caminho de uma leitura do equipamento.
    _runEffects(
      machine.onSample(
        ScaleSample(
          weightKg: value,
          raw: 'manual:${value.toStringAsFixed(3)}',
          stable: true,
        ),
        pricePerKg: pricePerKg,
      ),
    );
  }

  void _handleCommandKey(String key) {
    setState(() {
      commandController.text = nextKeypadValue(
        commandController.text,
        key,
        maximumLength: 32,
      );
    });
    commandFocusNode.requestFocus();
  }

  // ------------------------------------------------------------------- UI

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
      child: !started
          ? Padding(padding: const EdgeInsets.all(24), child: _setup())
          // Peso, lista de itens e código da comanda ficam juntos numa
          // coluna à esquerda — dedicada, não um apêndice estreito do
          // cardápio — porque é onde o operador passa a maior parte do
          // tempo: pesar, conferir os extras e ler a comanda. O cardápio
          // fica à direita, como destino de toque, não de leitura constante.
          : ScaleOperationGrid(
              items: _itemsPanel(),
              catalog: _catalog(),
              command: _commandPanel(),
            ),
    );
  }

  /// Cardápio de extras, no mesmo componente que o PDV usa.
  Widget _catalog() => ProductCatalogPanel(
    products: visibleExtras,
    allProducts: unitProducts,
    categories: extraCategories,
    selectedCategory: extrasCategory,
    search: extrasSearch,
    money: ValueFormatters.money,
    onSearchChanged: (value) => setState(() => extrasSearch = value),
    onCategoryChanged: (value) => setState(() => extrasCategory = value),
    onProductPressed: (product) => unawaited(_addExtra(product)),
  );

  /// Mesma pergunta do PDV padrão: variação, adicionais, quantidade e
  /// observação — antes só era possível empilhar +1 por toque, sem escolher
  /// nada do que o produto oferece.
  Future<void> _addExtra(Map<String, dynamic> product) async {
    final id = '${product['id']}';
    final config = await showProductConfigDialog(context, product);
    if (config == null) return;
    machine.addExtra(id, config.quantity.round());
    extraConfigs[id] = config;
  }

  Widget _setup() => Center(
    child: SizedBox(
      width: 620,
      child: SingleChildScrollView(
        child: AppSection(
          padding: EdgeInsets.zero,
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
                  isExpanded: true,
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
                  isExpanded: true,
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
                          child: Text(
                            '${item['name']} · ${item['port'] ?? ''}',
                          ),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => unawaited(_selectScale(value)),
                ),
                if (scaleId != null) ...[
                  const SizedBox(height: 14),
                  _scaleSetupCard(),
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
                              '${item['name']} · ${PrinterEndpoint.fromJson(item).label}',
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
                    'Produto: ${weighedProduct!['name']} · '
                    '${ValueFormatters.money(pricePerKg)}/kg',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ],
                if (errorMessage != null) _errorBox(),
                const SizedBox(height: 22),
                FilledButton.icon(
                  onPressed: loadingScales
                      ? null
                      : () => unawaited(_startStation()),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Iniciar estação'),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );

  /// Resumo do que a estação vai usar: porta, protocolo e tolerância.
  Widget _scaleSetupCard() {
    final scheme = Theme.of(context).colorScheme;
    final settings =
        selectedScale?['settings'] as Map<String, dynamic>? ?? const {};
    final port = configuredPort;
    final baudRate = '${settings['baudrate'] ?? 9600}';
    final protocol = ScaleProtocol.forId('${settings['protocol'] ?? ''}');
    final missingPort = port.isEmpty;
    final color = missingPort ? Colors.orange.shade800 : scheme.primary;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: AppTheme.radius,
        border: Border.all(
          color: missingPort
              ? color.withValues(alpha: .45)
              : scheme.outlineVariant,
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(
              color: color.withValues(alpha: .12),
              borderRadius: AppTheme.radius,
            ),
            child: Icon(
              missingPort
                  ? Icons.settings_input_component_outlined
                  : Icons.cable,
              color: color,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  missingPort
                      ? 'Balança sem porta cadastrada'
                      : 'Leitura local por $port',
                  style: const TextStyle(fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 3),
                Text(
                  missingPort
                      ? 'Informe a COM e o baud rate no cadastro. Sem isso só '
                            'o peso manual funciona nesta estação.'
                      : '$baudRate baud · ${protocol.label} · estabiliza em '
                            '$settleSeconds s',
                  style: TextStyle(
                    color: missingPort ? color : scheme.onSurfaceVariant,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Estado do vínculo com o equipamento durante a operação.
  Widget _linkCard() {
    final scheme = Theme.of(context).colorScheme;
    final (color, icon) = switch (linkStatus.state) {
      ScaleLinkState.connected => (Colors.green.shade700, Icons.sensors),
      ScaleLinkState.connecting => (
        scheme.onSurfaceVariant,
        Icons.settings_ethernet,
      ),
      ScaleLinkState.portBusy => (Colors.orange.shade800, Icons.lock_outline),
      ScaleLinkState.noResponse => (
        Colors.orange.shade800,
        Icons.hourglass_empty,
      ),
      ScaleLinkState.readError => (scheme.error, Icons.error_outline),
      ScaleLinkState.disconnected => (scheme.onSurfaceVariant, Icons.link_off),
    };
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: AppTheme.radius,
        border: Border.all(color: color.withValues(alpha: .4)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              linkStatus.message,
              style: TextStyle(
                color: color,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

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
        borderRadius: AppTheme.radius,
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
              borderRadius: AppTheme.radius,
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

  /// Coluna dos itens — o equivalente ao painel de pedido do PDV: peso,
  /// item pesado, extras (com excluir) e o total. A comanda em si (código,
  /// teclado, finalizar) mora em [_commandPanel], não aqui: pesar/escolher
  /// extras e ler a comanda são etapas distintas para o operador.
  Widget _itemsPanel() {
    final scheme = Theme.of(context).colorScheme;
    final waitingCommand = {
      HandsFreeState.waitingCommand,
      HandsFreeState.commandOverdue,
      HandsFreeState.failed,
    }.contains(machine.state);
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 0, 12),
      child: AppSection(
        padding: EdgeInsets.zero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _itemsHeader(),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
                children: [
                  _weightBlock(compact: waitingCommand),
                  // O estado da porta some da tela quando a balança está
                  // saudável e a etapa é outra: o que o operador precisa ver
                  // aí são os itens, não a conexão que já está funcionando.
                  if (!waitingCommand ||
                      linkStatus.state != ScaleLinkState.connected) ...[
                    const SizedBox(height: 10),
                    _linkCard(),
                  ],
                  const SizedBox(height: 14),
                  _cartItems(),
                  if (errorMessage != null) _errorBox(),
                ],
              ),
            ),
            Container(
              decoration: BoxDecoration(
                color: scheme.surfaceContainerLowest,
                border: Border(top: BorderSide(color: scheme.outlineVariant)),
              ),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
              child: _itemsFooter(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _itemsHeader() {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      color: scheme.surfaceContainerLowest,
      padding: const EdgeInsets.fromLTRB(16, 14, 10, 12),
      child: Row(
        children: [
          const Expanded(
            child: Text(
              'Balança rápida',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
            ),
          ),
          IconButton(
            tooltip: 'Trocar restaurante ou balança',
            onPressed: machine.state == HandsFreeState.creatingOrder
                ? null
                : () => unawaited(_stopStation()),
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
    );
  }

  /// Total e as ações ligadas ao peso (pegar/digitar/reimprimir) — as ações
  /// de comanda (finalizar/cancelar) ficam no rodapé de [_commandPanel].
  Widget _itemsFooter() {
    final item = machine.weighedItem;
    var total = item?.total ?? 0;
    for (final entry in machine.extras.entries) {
      if (entry.value <= 0) continue;
      final product = widget.products.cast<Map<String, dynamic>?>().firstWhere(
        (candidate) => '${candidate?['id']}' == entry.key,
        orElse: () => null,
      );
      total += ValueFormatters.number(product?['current_price']) * entry.value;
    }
    final showWeightActions =
        machine.state == HandsFreeState.idle ||
        machine.state == HandsFreeState.waitingWeight;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'TOTAL',
              style: TextStyle(fontWeight: FontWeight.w900, fontSize: 13),
            ),
            Text(
              ValueFormatters.money(total),
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
            ),
          ],
        ),
        if (showWeightActions) ...[
          const SizedBox(height: 10),
          ..._weightActions(),
        ],
      ],
    );
  }

  List<Widget> _weightActions() => [
    FilledButton.icon(
      onPressed: requestingWeight ? null : () => unawaited(_requestWeight()),
      icon: requestingWeight
          ? const SizedBox.square(
              dimension: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Colors.white,
              ),
            )
          : const Icon(Icons.download_rounded),
      label: Text(
        requestingWeight ? 'Solicitando...' : 'Pegar peso da balança',
      ),
    ),
    Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        TextButton.icon(
          onPressed: _enterManualWeight,
          style: TextButton.styleFrom(
            visualDensity: VisualDensity.compact,
            textStyle: const TextStyle(fontSize: 12),
          ),
          icon: const Icon(Icons.keyboard_alt_outlined, size: 16),
          label: const Text('Digitar peso'),
        ),
        if (lastPrintJobId != null)
          TextButton.icon(
            onPressed: reprinting
                ? null
                : () => unawaited(_reprintLastTicket()),
            style: TextButton.styleFrom(
              visualDensity: VisualDensity.compact,
              textStyle: const TextStyle(fontSize: 12),
            ),
            icon: const Icon(Icons.print_outlined, size: 16),
            label: const Text('Reimprimir'),
          ),
      ],
    ),
  ];

  /// Coluna da comanda, isolada à direita: código, teclado e a ação de
  /// finalizar/cancelar. Fora da etapa de leitura, mostra um estado neutro
  /// (aguardando peso) ou o resultado (finalizando/concluído).
  Widget _commandPanel() {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 12, 12, 12),
      child: AppSection(
        padding: EdgeInsets.zero,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _commandHeader(),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
                child: _commandBody(),
              ),
            ),
            Container(
              decoration: BoxDecoration(
                color: scheme.surfaceContainerLowest,
                border: Border(top: BorderSide(color: scheme.outlineVariant)),
              ),
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 14),
              child: _commandFooter(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _commandHeader() {
    final scheme = Theme.of(context).colorScheme;
    final code = commandController.text.trim();
    return Container(
      color: scheme.surfaceContainerLowest,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Comanda',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 2),
          Text(
            code.isEmpty ? 'Comanda não lida' : 'Comanda $code',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Widget _commandBody() {
    switch (machine.state) {
      case HandsFreeState.creatingOrder:
        return const Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child: Column(
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 10),
              Text(
                'Finalizando o pedido. Não retire a comanda.',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        );
      case HandsFreeState.completed:
        return const Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child: Column(
            children: [
              Icon(Icons.check_circle, size: 64, color: Colors.green),
              SizedBox(height: 8),
              Text(
                'Pedido lançado com sucesso.',
                textAlign: TextAlign.center,
                style: TextStyle(fontWeight: FontWeight.w800),
              ),
            ],
          ),
        );
      case HandsFreeState.waitingCommand:
      case HandsFreeState.commandOverdue:
      case HandsFreeState.failed:
        return _commandInput();
      case HandsFreeState.idle:
      case HandsFreeState.waitingWeight:
        return _commandPlaceholder();
    }
  }

  Widget _commandPlaceholder() {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 24),
      child: Column(
        children: [
          Icon(Icons.qr_code_scanner, size: 30, color: scheme.onSurfaceVariant),
          const SizedBox(height: 8),
          Text(
            'Pese o produto para liberar a leitura da comanda.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Widget _commandFooter() {
    if ({
      HandsFreeState.waitingCommand,
      HandsFreeState.commandOverdue,
      HandsFreeState.failed,
    }.contains(machine.state)) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: _commandActions(),
      );
    }
    if (machine.state == HandsFreeState.creatingOrder) {
      return const FilledButton(onPressed: null, child: Text('Finalizando...'));
    }
    if (machine.state == HandsFreeState.completed) {
      return const FilledButton(
        onPressed: null,
        child: Text('Pedido concluído'),
      );
    }
    return const SizedBox.shrink();
  }

  List<Widget> _commandActions() => [
    FilledButton.icon(
      onPressed: commandController.text.trim().isEmpty
          ? null
          : () => _runEffects(machine.onCommandRead(commandController.text)),
      icon: const Icon(Icons.check),
      label: const Text('Finalizar na comanda'),
    ),
    TextButton.icon(
      onPressed: () => _runEffects(machine.cancel()),
      icon: const Icon(Icons.close),
      label: const Text('Cancelar pesagem'),
    ),
  ];

  /// Peso ao vivo. Encolhe quando a etapa passa a ser a leitura da comanda —
  /// aí o que importa na tela é o campo do código, não mais a balança.
  Widget _weightBlock({required bool compact}) {
    final scheme = Theme.of(context).colorScheme;
    final item = machine.weighedItem;
    final weight = item?.weightKg ?? machine.currentWeightKg;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(vertical: compact ? 12 : 20),
      decoration: BoxDecoration(
        color: scheme.primaryContainer.withValues(alpha: .35),
        borderRadius: AppTheme.radius,
      ),
      child: Column(
        children: [
          Text(
            '${weight.toStringAsFixed(3)} kg',
            style: TextStyle(
              fontSize: compact ? 30 : 46,
              fontWeight: FontWeight.w900,
              color: scheme.primary,
            ),
          ),
          if (!compact) ...[
            const SizedBox(height: 6),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: LinearProgressIndicator(
                value: machine.isStable ? 1 : null,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              machine.isStable
                  ? 'Peso estável.'
                  : 'Aguardando leitura estável por $settleSeconds s...',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
          ],
        ],
      ),
    );
  }

  /// Item pesado + extras, na mesma leitura de um carrinho do PDV.
  Widget _cartItems() {
    final scheme = Theme.of(context).colorScheme;
    final item = machine.weighedItem;
    final selected = machine.extras.entries
        .where((entry) => entry.value > 0)
        .toList(growable: false);
    if (item == null && selected.isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Column(
          children: [
            Icon(
              Icons.shopping_basket_outlined,
              size: 30,
              color: scheme.onSurfaceVariant,
            ),
            const SizedBox(height: 8),
            Text(
              'Coloque o prato na balança.\nOs extras podem ser tocados no '
              'cardápio ao lado.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (item != null)
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            title: Text(
              '${weighedProduct?['name'] ?? 'Refeição por peso'}',
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            subtitle: Text(
              '${item.weightKg.toStringAsFixed(3)} kg × '
              '${ValueFormatters.money(item.pricePerKg)}/kg',
              style: const TextStyle(fontSize: 11),
            ),
            trailing: Text(
              ValueFormatters.money(item.total),
              style: const TextStyle(fontWeight: FontWeight.w900),
            ),
          ),
        for (final entry in selected) _extraLine(entry.key, entry.value),
      ],
    );
  }

  Widget _extraLine(String productId, int quantity) {
    final product = widget.products.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == productId,
      orElse: () => null,
    );
    final unit = ValueFormatters.number(product?['current_price']);
    final config = extraConfigs[productId];
    final details = _extraConfigSummary(product, config);
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      isThreeLine: details != null,
      title: Text(
        '${product?['name'] ?? 'Produto'}',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            ValueFormatters.money(unit),
            style: const TextStyle(fontSize: 11),
          ),
          if (details != null)
            Text(
              details,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 11),
            ),
        ],
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            visualDensity: VisualDensity.compact,
            onPressed: () {
              if (quantity <= 1) extraConfigs.remove(productId);
              machine.addExtra(productId, quantity - 1);
            },
            icon: const Icon(Icons.remove_circle_outline, size: 20),
          ),
          SizedBox(
            width: 24,
            child: Text(
              '$quantity',
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w900),
            ),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            onPressed: quantity >= 99
                ? null
                : () => machine.addExtra(productId, quantity + 1),
            icon: const Icon(Icons.add_circle_outline, size: 20),
          ),
        ],
      ),
    );
  }

  /// Resumo legível da variação/adicionais/observação escolhidos, para o
  /// operador conferir sem reabrir o diálogo.
  String? _extraConfigSummary(
    Map<String, dynamic>? product,
    ProductConfigResult? config,
  ) {
    if (config == null) return null;
    final parts = <String>[];
    if (config.variationId != null) {
      final variations = (product?['variations'] as List? ?? [])
          .cast<Map<String, dynamic>>();
      final variation = variations.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == config.variationId,
        orElse: () => null,
      );
      if (variation != null) parts.add('${variation['name']}');
    }
    if (config.addonIds.isNotEmpty) {
      final addons = (product?['addons'] as List? ?? [])
          .cast<Map<String, dynamic>>();
      final names = config.addonIds
          .map(
            (id) => addons.cast<Map<String, dynamic>?>().firstWhere(
              (item) => '${item?['id']}' == id,
              orElse: () => null,
            ),
          )
          .whereType<Map<String, dynamic>>()
          .map((item) => '${item['name']}');
      parts.addAll(names);
    }
    if (config.customerNote.isNotEmpty) parts.add(config.customerNote);
    return parts.isEmpty ? null : parts.join(' · ');
  }

  /// Campo do código da comanda e teclado touch, na etapa de leitura.
  Widget _commandInput() {
    final overdue = machine.state == HandsFreeState.commandOverdue;
    final now = DateTime.now();
    final remaining =
        machine.remainingForCancel(now) ?? machine.remainingForCommand(now);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (remaining != null) ...[
          _countdown(remaining, overdue: overdue),
          const SizedBox(height: 10),
        ],
        if (machine.failureMessage != null) ...[
          _inlineWarning(machine.failureMessage!),
          const SizedBox(height: 10),
        ],
        TextField(
          controller: commandController,
          focusNode: commandFocusNode,
          autofocus: true,
          textInputAction: TextInputAction.done,
          inputFormatters: [LengthLimitingTextInputFormatter(32)],
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => _submitCommandInput(),
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
          decoration: InputDecoration(
            labelText: 'Código da comanda',
            helperText: scannerService != null
                ? 'Aproxime a comanda do leitor desta janela.'
                : 'Digite ou leia a comanda e pressione Enter.',
            helperMaxLines: 2,
          ),
        ),
        const SizedBox(height: 12),
        TouchKeypad(onKey: _handleCommandKey),
      ],
    );
  }

  Widget _countdown(Duration remaining, {required bool overdue}) {
    final scheme = Theme.of(context).colorScheme;
    final color = overdue ? scheme.error : scheme.onSurfaceVariant;
    return Text(
      overdue
          ? 'A pesagem será cancelada em ${remaining.inSeconds} s. '
                'Leia a comanda para concluir.'
          : 'Tempo para a comanda: ${remaining.inSeconds} s',
      textAlign: TextAlign.center,
      style: TextStyle(
        color: color,
        fontWeight: FontWeight.w800,
        fontSize: overdue ? 15 : 13,
      ),
    );
  }

  Widget _inlineWarning(String message) => Container(
    padding: const EdgeInsets.all(11),
    decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.errorContainer,
      borderRadius: AppTheme.radius,
    ),
    child: Text(
      message,
      textAlign: TextAlign.center,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onErrorContainer,
        fontWeight: FontWeight.w700,
      ),
    ),
  );

  Widget _errorBox() => Padding(
    padding: const EdgeInsets.only(top: 14),
    child: Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.errorContainer,
        borderRadius: AppTheme.radius,
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
}

/// Grade operacional da Balança Rápida: resumo 25%, catálogo 50% e
/// comanda 25%. `Expanded` é o equivalente adequado a uma grade de colunas
/// para painéis únicos no Flutter.
class ScaleOperationGrid extends StatelessWidget {
  const ScaleOperationGrid({
    super.key,
    required this.items,
    required this.catalog,
    required this.command,
  });

  final Widget items;
  final Widget catalog;
  final Widget command;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Expanded(key: const Key('scale-items-column'), child: items),
      Expanded(key: const Key('scale-catalog-column'), flex: 2, child: catalog),
      Expanded(key: const Key('scale-command-column'), child: command),
    ],
  );
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
      borderRadius: AppTheme.radius,
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
