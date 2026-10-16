import 'package:flutter/foundation.dart';

import '../../../core/hardware/scale/scale_sample.dart';
import 'busca_de_peso.dart';

/// Etapas do fluxo automatizado da Balança Rápida.
enum HandsFreeState {
  /// Estação parada, aguardando configuração ou início.
  idle,

  /// Estado 1: esperando um peso válido e estável.
  waitingWeight,

  /// Peso registrado, aguardando o operador escolher o produto por quilo
  /// (modo "Escolher o produto a cada pesagem").
  choosingProduct,

  /// Estado 2: item pesado registrado, aguardando a leitura da comanda.
  waitingCommand,

  /// Estado 3: lançando a anotação na comanda e imprimindo.
  launching,

  /// Lançamento concluído; a estação volta sozinha ao Estado 1.
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

  /// A interface deve lançar a pesagem na comanda.
  launchIntoCommand,

  /// A operação temporária foi descartada.
  operationCancelled,

  /// A tela está em 0 sem leitura nova: pedir o peso à balança.
  fetchWeight,

  /// A interface deve perguntar qual produto por quilo foi pesado.
  chooseProduct,
}

/// Item pesado que aguarda a comanda.
class WeighedItem {
  const WeighedItem({
    required this.weightKg,
    required this.pricePerKg,
    required this.capturedAt,
    this.raw,
    this.productId,
  });

  final double weightKg;
  final double pricePerKg;
  final DateTime capturedAt;

  /// Quadro serial que originou a leitura, guardado para auditoria.
  final String? raw;

  /// Produto escolhido na estação; `null` = o vinculado à balança.
  final String? productId;

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
    this.minimumWeightKg = 0.005,
    this.cancelOnZeroDuringCommand = false,
  });

  /// Tempo máximo aguardando a comanda antes do cancelamento automático.
  ///
  /// Único temporizador do fluxo — o mesmo valor configurado em
  /// Preferências. Havia um segundo período fixo de 10s ("grace period")
  /// somado a este depois de esgotado: configurar 10s no terminal cancelava
  /// de fato aos 20s, e ninguém que ajustou aquele número esperava isso.
  final Duration commandTimeout;

  /// Abaixo deste valor o prato é considerado vazio.
  final double minimumWeightKg;

  /// Cancelar a operação quando o prato é retirado antes de ler a comanda.
  ///
  /// O padrão é `false` porque retirar o prato logo após a pesagem é o
  /// comportamento normal do cliente: cancelar aí descartaria vendas
  /// legítimas. O abandono real é tratado pelo timeout configurável.
  final bool cancelOnZeroDuringCommand;

  /// Comanda automática: o servidor escolhe a próxima comanda livre
  /// (`fila_da_comanda.py`). Peso estável vai direto ao lançamento — não há
  /// cartão a esperar, e por isso também não há prazo de comanda.
  bool _comandaAutomatica = false;
  bool get comandaAutomatica => _comandaAutomatica;

  /// Na comanda automática, ESTA passagem pede o cartão (o cliente com dois
  /// pratos: o segundo vai para a comanda do primeiro). Vale uma passagem só:
  /// lançada ou cancelada, volta ao automático.
  bool _pedirComandaNestaPassagem = false;
  bool get pedirComandaNestaPassagem => _pedirComandaNestaPassagem;
  bool get automaticaNestaPassagem =>
      _comandaAutomatica && !_pedirComandaNestaPassagem;

  /// Liga/desliga o "pedir a comanda" — só antes do lançamento, no automático.
  void alternarPedirComanda() {
    final antesDoLancamento =
        _state == HandsFreeState.waitingWeight ||
        _state == HandsFreeState.choosingProduct;
    if (!_comandaAutomatica || !antesDoLancamento) return;
    _pedirComandaNestaPassagem = !_pedirComandaNestaPassagem;
    notifyListeners();
  }

  /// Escolher o produto a cada pesagem, ignorando o vinculado à balança.
  bool _escolherProduto = false;
  bool get escolherProduto => _escolherProduto;

  HandsFreeState _state = HandsFreeState.idle;
  WeighedItem? _weighedItem;
  final Map<String, int> _extras = {};
  String? _commandCode;
  String? _failureMessage;
  DateTime? _commandDeadline;
  double _currentWeightKg = 0;

  /// Peso do prato que ACABOU de ser lançado e pode ainda estar na balança.
  /// Enquanto ele aparecer, a tela mostra 0 e nada é capturado — senão o
  /// mesmo prato virava pesagem nova para a próxima comanda lida.
  double? _pesoJaLancado;
  static const _mesmoPratoKg = 0.010;
  bool _stable = false;

  /// O prato saiu da balança em algum momento depois de pesado.
  ///
  /// Balança que só transmite quando o peso MUDA manda o zero uma vez — e o
  /// cliente costuma tirar o prato durante o "Pedido lançado". Sem lembrar
  /// desse zero, o filtro do prato lançado era armado depois dele e nunca
  /// mais soltava: o próximo prato de peso parecido ficava em 0 para sempre.
  bool _retiradoDepoisDaPesagem = false;

  /// A última amostra descartada pelo filtro, para o "Pesar de novo".
  ScaleSample? _amostraRetida;

  /// A última leitura que chegou enquanto lançava ou mostrava "lançado":
  /// [readyForNext] a reprocessa, em vez de a tela voltar em 0.
  ScaleSample? _ultimaDoLancamento;

  final _buscaDePeso = BuscaDePeso();

  /// A tela está em 0 porque o peso na balança é o do prato já lançado.
  bool get aguardandoRetirada =>
      _state == HandsFreeState.waitingWeight && _pesoJaLancado != null;

  /// O peso que está sendo ignorado (o do prato lançado), para a tela dizer.
  double? get pesoRetido =>
      aguardandoRetirada ? _amostraRetida?.weightKg : null;

  HandsFreeState get state => _state;
  WeighedItem? get weighedItem => _weighedItem;
  Map<String, int> get extras => Map.unmodifiable(_extras);
  String? get commandCode => _commandCode;
  String? get failureMessage => _failureMessage;
  double get currentWeightKg => _currentWeightKg;
  bool get isStable => _stable;

  /// Quanto falta para o cancelamento automático, quando aplicável.
  Duration? remainingForCommand(DateTime now) {
    final deadline = _commandDeadline;
    if (deadline == null || _state != HandsFreeState.waitingCommand) {
      return null;
    }
    final remaining = deadline.difference(now);
    return remaining.isNegative ? Duration.zero : remaining;
  }

  bool get canAcceptCommand =>
      _state == HandsFreeState.waitingCommand ||
      _state == HandsFreeState.failed;

  /// Coloca a estação no Estado 1, no modo escolhido ao iniciar.
  List<HandsFreeEffect> start({
    bool comandaAutomatica = false,
    bool escolherProduto = false,
  }) {
    _comandaAutomatica = comandaAutomatica;
    _escolherProduto = escolherProduto;
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
    if (_state == HandsFreeState.launching ||
        _state == HandsFreeState.completed) {
      _ultimaDoLancamento = sample;
    }
    final empty = sample.weightKg <= minimumWeightKg;
    final pesado = _weighedItem?.weightKg;
    if (pesado != null) {
      // "Fora da balança AGORA": zerou, ou há outro peso nela. Devolvido o
      // mesmo prato, volta a valer o filtro — senão ele seria cobrado de novo.
      _retiradoDepoisDaPesagem =
          empty || (sample.weightKg - pesado).abs() > _mesmoPratoKg;
    }
    final jaLancado = _pesoJaLancado;
    if (_state == HandsFreeState.waitingWeight && jaLancado != null) {
      // Zerou (prato retirado) ou chegou OUTRO peso (balança que não manda o
      // zero): libera. O mesmo peso é o prato antigo — ignora.
      if (!empty && (sample.weightKg - jaLancado).abs() <= _mesmoPratoKg) {
        _buscaDePeso.amostra(sample.at, conhecido: true);
        if (_amostraRetida == null) {
          _amostraRetida = sample;
          notifyListeners();
        } else {
          _amostraRetida = sample;
        }
        return const [];
      }
      _pesoJaLancado = null;
      _amostraRetida = null;
    }
    _currentWeightKg = sample.weightKg;
    _stable = sample.stable == true;
    _buscaDePeso.amostra(sample.at, conhecido: empty || _stable);
    final effects = <HandsFreeEffect>[];

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
          _retiradoDepoisDaPesagem = false;
          effects.add(HandsFreeEffect.successSound);
          if (_escolherProduto) {
            _state = HandsFreeState.choosingProduct;
            effects.add(HandsFreeEffect.chooseProduct);
          } else {
            effects.addAll(_seguirParaComanda(sample.at));
          }
        }
      case HandsFreeState.waitingCommand:
        if (empty && cancelOnZeroDuringCommand) {
          effects.addAll(_cancelToWaiting());
        }
      case HandsFreeState.idle:
      case HandsFreeState.choosingProduct:
      case HandsFreeState.launching:
      case HandsFreeState.completed:
      case HandsFreeState.failed:
        break;
    }
    notifyListeners();
    return effects;
  }

  /// Avança o relógio da máquina; a interface chama a cada segundo.
  ///
  /// Um único prazo: esgotado o tempo de comanda, cancela na hora — sem um
  /// segundo período de espera por trás. Esperando peso, pede a leitura à
  /// balança quando a tela ficou em 0 sem amostra nova ([BuscaDePeso]).
  List<HandsFreeEffect> tick(DateTime now) {
    if (_state == HandsFreeState.waitingWeight) {
      return _buscaDePeso.devePedir(now)
          ? const [HandsFreeEffect.fetchWeight]
          : const [];
    }
    if (_state != HandsFreeState.waitingCommand) return const [];
    final deadline = _commandDeadline;
    if (deadline == null || now.isBefore(deadline)) return const [];
    final effects = [HandsFreeEffect.alertSound, ..._cancelToWaiting()];
    notifyListeners();
    return effects;
  }

  /// Recebe um código lido pelo scanner vinculado ou digitado no teclado touch.
  List<HandsFreeEffect> onCommandRead(String rawCode) {
    final code = rawCode.trim();
    // No modo automático quem escolhe a comanda é o servidor: um cartão lido
    // aqui não tem para onde ir.
    if (code.isEmpty || automaticaNestaPassagem) {
      return const [HandsFreeEffect.alertSound];
    }
    if (!canAcceptCommand) {
      // Uma leitura fora da etapa certa é ignorada com aviso sonoro para não
      // lançar a comanda em uma operação que não existe.
      return const [HandsFreeEffect.alertSound];
    }
    if (_weighedItem == null) return const [HandsFreeEffect.alertSound];
    if (_state == HandsFreeState.launching) {
      return const [HandsFreeEffect.alertSound];
    }

    _commandCode = code;
    _failureMessage = null;
    _state = HandsFreeState.launching;
    _commandDeadline = null;
    notifyListeners();
    return const [
      HandsFreeEffect.successSound,
      HandsFreeEffect.launchIntoCommand,
    ];
  }

  /// A anotação entrou na comanda e a etiqueta foi despachada.
  ///
  /// [comanda] é o número que o servidor escolheu no modo automático, para a
  /// tela mostrar onde o prato foi parar.
  List<HandsFreeEffect> onLaunched({String? comanda}) {
    if (comanda != null) _commandCode = comanda;
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

  /// O operador escolheu o produto por quilo do prato pesado.
  ///
  /// O preço do kg é o do produto escolhido, congelado agora — como o da
  /// balança é congelado na estabilização.
  List<HandsFreeEffect> onProdutoEscolhido({
    required String productId,
    required double pricePerKg,
    required DateTime now,
  }) {
    final item = _weighedItem;
    if (_state != HandsFreeState.choosingProduct || item == null) {
      return const [];
    }
    _weighedItem = WeighedItem(
      weightKg: item.weightKg,
      pricePerKg: pricePerKg,
      capturedAt: item.capturedAt,
      raw: item.raw,
      productId: productId,
    );
    final effects = _seguirParaComanda(now);
    notifyListeners();
    return effects;
  }

  /// Depois do peso (e do produto): lança direto ou espera o cartão.
  List<HandsFreeEffect> _seguirParaComanda(DateTime now) {
    if (automaticaNestaPassagem) {
      _state = HandsFreeState.launching;
      return const [HandsFreeEffect.launchIntoCommand];
    }
    _state = HandsFreeState.waitingCommand;
    _commandDeadline = now.add(commandTimeout);
    return const [];
  }

  /// Modo automático: lança de novo a pesagem que falhou (ex.: nenhuma
  /// comanda livre). A mesma pesagem, sem pesar outra vez.
  List<HandsFreeEffect> tentarDeNovo() {
    if (!automaticaNestaPassagem ||
        _state != HandsFreeState.failed ||
        _weighedItem == null) {
      return const [];
    }
    _failureMessage = null;
    _state = HandsFreeState.launching;
    notifyListeners();
    return const [HandsFreeEffect.launchIntoCommand];
  }

  /// Após o aviso de sucesso, volta ao Estado 1 para o próximo cliente.
  ///
  /// A última leitura que chegou ENQUANTO lançava é reprocessada aqui, com
  /// [pricePerKg]. A balança que só transmite quando o peso muda manda o
  /// prato novo uma vez só — e, jogada fora, a tela voltava em 0 com o prato
  /// em cima, travada. Se a leitura for o prato lançado (mesmo peso, sem ter
  /// saído), o filtro abaixo a segura e a tela mostra o "Pesar de novo".
  List<HandsFreeEffect> readyForNext({double? pricePerKg}) {
    // Prato já retirado (o zero chegou enquanto lançava): nada a proteger.
    final lancado = _retiradoDepoisDaPesagem ? null : _weighedItem?.weightKg;
    final pendente = _ultimaDoLancamento;
    _state = HandsFreeState.waitingWeight;
    _resetOperation();
    _pesoJaLancado = lancado;
    if (pendente == null || pricePerKg == null) {
      notifyListeners();
      return const [];
    }
    return onSample(pendente, pricePerKg: pricePerKg);
  }

  /// O operador confirma que o peso na balança é um prato NOVO.
  ///
  /// Saída para a balança que não manda zero nenhum e recebe outro prato do
  /// mesmo peso: sem ela, a estação ficava presa até reiniciar o PDV. A
  /// amostra retida é reprocessada na hora — a balança que só transmite
  /// quando muda não mandaria outra.
  List<HandsFreeEffect> pesarDeNovo({required double pricePerKg}) {
    if (!aguardandoRetirada) return const [];
    final retida = _amostraRetida;
    _pesoJaLancado = null;
    _amostraRetida = null;
    if (retida == null) {
      notifyListeners();
      return const [];
    }
    return onSample(retida, pricePerKg: pricePerKg);
  }

  /// Cancelamento explícito pelo operador.
  List<HandsFreeEffect> cancel() {
    if (_state == HandsFreeState.launching) return const [];
    final pesado = _weighedItem?.weightKg;
    final effects = _cancelToWaiting();
    // Automática: o prato cancelado ainda está na balança, e a próxima
    // amostra estável o LANÇARIA na hora. Ele fica retido até sair (ou o
    // "Pesar de novo"). Na escolha de produto não: ali o próximo passo é só
    // perguntar de novo, e reter prendia o prato de quem apertou Esc sem
    // querer.
    if (_comandaAutomatica) _pesoJaLancado = pesado;
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
    _currentWeightKg = 0;
    _stable = false;
    _pesoJaLancado = null;
    _retiradoDepoisDaPesagem = false;
    _amostraRetida = null;
    _ultimaDoLancamento = null;
    _pedirComandaNestaPassagem = false;
    _buscaDePeso.recomecar();
  }
}
