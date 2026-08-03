import 'package:flutter/foundation.dart';

import '../../../core/hardware/scale/scale_sample.dart';

/// Etapas do fluxo automatizado da Balança Rápida.
enum HandsFreeState {
  /// Estação parada, aguardando configuração ou início.
  idle,

  /// Estado 1: esperando um peso válido e estável.
  waitingWeight,

  /// Estado 2: item pesado registrado, aguardando a leitura da comanda.
  waitingCommand,

  /// Estado 2 em alerta: o tempo de comanda esgotou e há um período curto de
  /// confirmação antes do cancelamento automático.
  commandOverdue,

  /// Estado 3: criando o pedido e imprimindo.
  creatingOrder,

  /// Pedido concluído; a estação volta sozinha ao Estado 1.
  completed,

  /// A criação falhou; o operador pode reler a comanda.
  failed,
}

/// Efeitos que a interface deve executar em resposta a uma transição.
enum HandsFreeEffect {
  /// Alerta sonoro de atenção (timeout, leitura recusada).
  alertSound,

  /// Confirmação sonora curta (leitura aceita).
  successSound,

  /// A interface deve disparar a criação do pedido.
  createOrder,

  /// A operação temporária foi descartada.
  operationCancelled,
}

/// Item pesado que aguarda a comanda.
class WeighedItem {
  const WeighedItem({
    required this.weightKg,
    required this.pricePerKg,
    required this.capturedAt,
    this.raw,
  });

  final double weightKg;
  final double pricePerKg;
  final DateTime capturedAt;

  /// Quadro serial que originou a leitura, guardado para auditoria.
  final String? raw;

  double get total => weightKg * pricePerKg;
}

/// Fluxo hands-free da pesagem, isolado da interface.
///
/// A máquina não conhece widgets nem API: recebe amostras da balança e
/// leituras do scanner e decide a próxima etapa. Isso permite testar o
/// comportamento de estabilização, timeout e cancelamento sem hardware.
///
/// O relógio é injetado por [tick] para que os testes controlem o tempo.
class HandsFreeMachine extends ChangeNotifier {
  HandsFreeMachine({
    required this.commandTimeout,
    this.gracePeriod = const Duration(seconds: 10),
    this.minimumWeightKg = 0.005,
    this.cancelOnZeroDuringCommand = false,
  });

  /// Tempo máximo aguardando a comanda antes do alerta.
  final Duration commandTimeout;

  /// Período de confirmação entre o alerta e o cancelamento automático.
  final Duration gracePeriod;

  /// Abaixo deste valor o prato é considerado vazio.
  final double minimumWeightKg;

  /// Cancelar a operação quando o prato é retirado antes de ler a comanda.
  ///
  /// O padrão é `false` porque retirar o prato logo após a pesagem é o
  /// comportamento normal do cliente: cancelar aí descartaria vendas
  /// legítimas. O abandono real é tratado pelo timeout configurável.
  final bool cancelOnZeroDuringCommand;

  HandsFreeState _state = HandsFreeState.idle;
  WeighedItem? _weighedItem;
  final Map<String, int> _extras = {};
  String? _commandCode;
  String? _failureMessage;
  DateTime? _commandDeadline;
  DateTime? _cancelDeadline;
  double _currentWeightKg = 0;
  bool _stable = false;

  HandsFreeState get state => _state;
  WeighedItem? get weighedItem => _weighedItem;
  Map<String, int> get extras => Map.unmodifiable(_extras);
  String? get commandCode => _commandCode;
  String? get failureMessage => _failureMessage;
  double get currentWeightKg => _currentWeightKg;
  bool get isStable => _stable;

  /// Quanto falta para o alerta de comanda, quando aplicável.
  Duration? remainingForCommand(DateTime now) {
    final deadline = _commandDeadline;
    if (deadline == null || _state != HandsFreeState.waitingCommand) {
      return null;
    }
    final remaining = deadline.difference(now);
    return remaining.isNegative ? Duration.zero : remaining;
  }

  /// Quanto falta para o cancelamento automático durante o alerta.
  Duration? remainingForCancel(DateTime now) {
    final deadline = _cancelDeadline;
    if (deadline == null || _state != HandsFreeState.commandOverdue) {
      return null;
    }
    final remaining = deadline.difference(now);
    return remaining.isNegative ? Duration.zero : remaining;
  }

  bool get canAcceptCommand =>
      _state == HandsFreeState.waitingCommand ||
      _state == HandsFreeState.commandOverdue ||
      _state == HandsFreeState.failed;

  /// Coloca a estação no Estado 1.
  List<HandsFreeEffect> start() {
    _state = HandsFreeState.waitingWeight;
    _resetOperation();
    notifyListeners();
    return const [];
  }

  /// Volta a estação ao repouso (troca de balança, saída da tela).
  List<HandsFreeEffect> stop() {
    _state = HandsFreeState.idle;
    _resetOperation();
    notifyListeners();
    return const [];
  }

  /// Processa uma amostra vinda da balança.
  ///
  /// [pricePerKg] entra aqui porque o preço precisa ser congelado no exato
  /// momento da estabilização: uma alteração de tabela durante a pesagem não
  /// pode mudar o valor já mostrado ao cliente.
  List<HandsFreeEffect> onSample(
    ScaleSample sample, {
    required double pricePerKg,
  }) {
    _currentWeightKg = sample.weightKg;
    _stable = sample.stable == true;
    final effects = <HandsFreeEffect>[];
    final empty = sample.weightKg <= minimumWeightKg;

    switch (_state) {
      case HandsFreeState.waitingWeight:
        // Nunca avança com o prato vazio nem com peso ainda oscilando.
        if (!empty && _stable) {
          _weighedItem = WeighedItem(
            weightKg: sample.weightKg,
            pricePerKg: pricePerKg,
            capturedAt: sample.at,
            raw: sample.raw,
          );
          _state = HandsFreeState.waitingCommand;
          _commandDeadline = sample.at.add(commandTimeout);
          _cancelDeadline = null;
          effects.add(HandsFreeEffect.successSound);
        }
      case HandsFreeState.waitingCommand:
      case HandsFreeState.commandOverdue:
        if (empty && cancelOnZeroDuringCommand) {
          effects.addAll(_cancelToWaiting());
        }
      case HandsFreeState.idle:
      case HandsFreeState.creatingOrder:
      case HandsFreeState.completed:
      case HandsFreeState.failed:
        break;
    }
    notifyListeners();
    return effects;
  }

  /// Avança o relógio da máquina; a interface chama a cada segundo.
  List<HandsFreeEffect> tick(DateTime now) {
    final effects = <HandsFreeEffect>[];
    if (_state == HandsFreeState.waitingCommand) {
      final deadline = _commandDeadline;
      if (deadline != null && !now.isBefore(deadline)) {
        _state = HandsFreeState.commandOverdue;
        _cancelDeadline = now.add(gracePeriod);
        effects.add(HandsFreeEffect.alertSound);
        notifyListeners();
      }
      return effects;
    }
    if (_state == HandsFreeState.commandOverdue) {
      final deadline = _cancelDeadline;
      if (deadline != null && !now.isBefore(deadline)) {
        effects.addAll(_cancelToWaiting());
        notifyListeners();
      }
    }
    return effects;
  }

  /// Recebe um código lido pelo scanner vinculado ou digitado no teclado touch.
  List<HandsFreeEffect> onCommandRead(String rawCode) {
    final code = rawCode.trim();
    if (code.isEmpty) return const [HandsFreeEffect.alertSound];
    if (!canAcceptCommand) {
      // Uma leitura fora da etapa certa é ignorada com aviso sonoro para não
      // lançar a comanda em uma operação que não existe.
      return const [HandsFreeEffect.alertSound];
    }
    if (_weighedItem == null) return const [HandsFreeEffect.alertSound];
    if (_state == HandsFreeState.creatingOrder) {
      return const [HandsFreeEffect.alertSound];
    }

    _commandCode = code;
    _failureMessage = null;
    _state = HandsFreeState.creatingOrder;
    _commandDeadline = null;
    _cancelDeadline = null;
    notifyListeners();
    return const [HandsFreeEffect.successSound, HandsFreeEffect.createOrder];
  }

  /// O pedido foi criado e o cupom despachado.
  List<HandsFreeEffect> onOrderCreated() {
    _state = HandsFreeState.completed;
    notifyListeners();
    return const [];
  }

  /// A criação falhou; a comanda pode ser lida novamente.
  List<HandsFreeEffect> onOrderFailed(String message) {
    _failureMessage = message;
    _state = HandsFreeState.failed;
    _commandCode = null;
    // O item pesado é preservado de propósito: a venda não pode ser perdida
    // por uma recusa temporária do servidor ou da impressora.
    notifyListeners();
    return const [HandsFreeEffect.alertSound];
  }

  /// Após o aviso de sucesso, volta ao Estado 1 para o próximo cliente.
  List<HandsFreeEffect> readyForNext() {
    _state = HandsFreeState.waitingWeight;
    _resetOperation();
    notifyListeners();
    return const [];
  }

  /// Cancelamento explícito pelo operador.
  List<HandsFreeEffect> cancel() {
    if (_state == HandsFreeState.creatingOrder) return const [];
    final effects = _cancelToWaiting();
    notifyListeners();
    return effects;
  }

  void addExtra(String productId, int quantity) {
    if (quantity <= 0) {
      _extras.remove(productId);
    } else {
      _extras[productId] = quantity;
    }
    notifyListeners();
  }

  List<HandsFreeEffect> _cancelToWaiting() {
    _state = HandsFreeState.waitingWeight;
    _resetOperation();
    return const [HandsFreeEffect.operationCancelled];
  }

  void _resetOperation() {
    _weighedItem = null;
    _extras.clear();
    _commandCode = null;
    _failureMessage = null;
    _commandDeadline = null;
    _cancelDeadline = null;
    _stable = false;
  }
}
