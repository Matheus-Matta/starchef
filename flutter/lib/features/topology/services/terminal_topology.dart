import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/storage/local_preferences.dart';
import '../../devices/services/local_device_agent.dart';
import '../data/local_topology_store.dart';
import '../domain/local_topology_config.dart';
import 'local_topology_service.dart';

/// Quem este terminal é para o relay: conta, operador e unidade.
///
/// A unidade é a única parte que pode chegar depois — ela vem do bootstrap de
/// dados, e é exatamente por isso que ela não pode bloquear o pareamento.
class TopologyIdentity {
  const TopologyIdentity({
    required this.accessToken,
    required this.accountId,
    required this.actorId,
    this.restaurantId = '',
    this.refreshToken = '',
    this.actorName = '',
    this.terminalName = '',
  });

  final String accessToken;
  final String accountId;
  final String actorId;
  final String restaurantId;

  /// Refresh deste terminal, enviado junto da operação encaminhada.
  ///
  /// Um Caixa Secundário não fala com o servidor — nem para renovar o próprio
  /// token. Quem renova, quando a operação dele espera muito na fila do
  /// principal, é o principal, com este refresh.
  final String refreshToken;

  /// Nome do operador e do terminal, para o registro que o principal grava
  /// antes de a nuvem confirmar.
  final String actorName;
  final String terminalName;

  /// Dá para assinar uma requisição ao Caixa Principal?
  bool get canPair =>
      accountId.trim().isNotEmpty && actorId.trim().isNotEmpty;
}

/// O papel deste terminal na rede local, decidido **antes** de qualquer dado.
///
/// É a correção de uma inversão que deixava o Caixa Secundário sem conexão
/// nenhuma: o relay só era ligado depois que o PDV terminava de carregar
/// restaurantes e cardápio, e num secundário essa carga é justamente o que
/// depende do Caixa Principal. Sem nuvem alcançável (ou sem cache local, num
/// terminal recém-instalado) a carga falhava, o relay nunca era ligado, e o
/// terminal passava o expediente tentando reconectar na nuvem — inclusive
/// abrindo o WebSocket do agente de impressão, que só o principal deve manter.
/// Quem estava na frente do caixa via "reconectando" para sempre e nenhuma
/// tentativa de falar com o principal.
///
/// O papel do terminal é uma decisão **local**: modo, endereço do principal e
/// chave de pareamento vivem no SQLite e no cofre deste computador. Nada disso
/// precisa da nuvem, então nada disso espera por ela.
class TerminalTopology extends ChangeNotifier {
  TerminalTopology({
    required this.api,
    required this.deviceAgent,
    required TopologyIdentity Function() readIdentity,
    required LocalTopologyStore Function() createStore,
    this.preferences,
  }) : _readIdentity = readIdentity,
       _createStore = createStore;

  final ApiClient api;
  final LocalDeviceAgent deviceAgent;

  /// Onde fica registrado o papel com que este terminal operou por último.
  /// Ver [LocalPreferences.servedAsPrincipal].
  final LocalPreferences? preferences;
  final TopologyIdentity Function() _readIdentity;
  final LocalTopologyStore Function() _createStore;

  LocalTopologyService? _service;
  Future<void>? _starting;
  bool _closed = false;

  LocalTopologyService? get service => _service;
  LocalTopologyConfig? get config => _service?.config;

  LocalTopologyStatus get status =>
      _service?.status ??
      const LocalTopologyStatus(
        phase: LocalTopologyPhase.starting,
        message: 'Preparando rede local...',
      );

  /// Este terminal é um Caixa Secundário, que depende do principal para gravar.
  bool get isClient => config?.mode == LocalTopologyMode.client;

  /// O principal respondeu ao último teste de conexão.
  bool get isClientReady =>
      status.phase == LocalTopologyPhase.clientReady;

  /// Só o principal fala com a nuvem — e só ele imprime pelos `PrintJob` dela.
  bool get servesCloud => !isClient;

  /// Liga (ou atualiza) a rede local deste terminal.
  ///
  /// Idempotente e seguro de chamar cedo: quando a unidade ainda não é
  /// conhecida, o terminal já assume o papel gravado e só termina de se
  /// identificar quando o [restaurantId] chega.
  Future<void> ensure({String? restaurantId}) {
    final pending = _starting;
    if (pending != null) return pending;
    final started = _ensure(restaurantId);
    _starting = started;
    return started.whenComplete(() {
      if (identical(_starting, started)) _starting = null;
    });
  }

  Future<void> _ensure(String? restaurantId) async {
    if (_closed) return;
    final identity = _readIdentity();
    final unit = (restaurantId ?? identity.restaurantId).trim();

    final existing = _service;
    if (existing != null) {
      if (unit.isNotEmpty) existing.updateRestaurant(unit);
      _syncDeviceAgent();
      return;
    }
    // Sem conta e operador não há como assinar nada: a rede local espera a
    // sessão, não o carregamento dos dados.
    if (!identity.canPair) return;

    final service = LocalTopologyService(
      api: api,
      accessToken: identity.accessToken,
      refreshToken: identity.refreshToken,
      accountId: identity.accountId,
      actorId: identity.actorId,
      actorName: identity.actorName,
      terminalName: identity.terminalName,
      restaurantId: unit,
      store: _createStore(),
      // Quem imprime em nome de um nó sem impressora (o app do garçom) é
      // este terminal, e só faz sentido com o mesmo agente que já fala com as
      // impressoras físicas.
      deviceAgent: deviceAgent,
    );
    try {
      await service.start();
    } catch (_) {
      await service.shutdown();
      rethrow;
    }
    if (_closed) {
      await service.shutdown();
      return;
    }
    _service = service;
    service.addListener(_onServiceChanged);
    _onServiceChanged();
  }

  Future<void> reconfigure(LocalTopologyConfig next) async {
    final service = _service;
    if (service == null) {
      throw StateError(
        'A rede local ainda não foi iniciada nesta sessão.',
      );
    }
    await service.reconfigure(next);
    _onServiceChanged();
  }

  void _onServiceChanged() {
    _syncDeviceAgent();
    notifyListeners();
  }

  /// O agente de impressão é do Caixa Principal.
  ///
  /// Num secundário ele abriria um WebSocket com a nuvem e ficaria
  /// reconectando sem parar — a fila de impressão da loja é servida pelo
  /// principal, que é quem tem as impressoras cadastradas para si.
  void _syncDeviceAgent() {
    final current = _service;
    final config = current?.config;
    final identity = _readIdentity();
    final restaurant = identity.restaurantId.trim();

    // Uma linha por decisão: é o agente quem imprime a comanda de pedido novo
    // (o `PrintJob` do backend), enquanto recibo e nota de teste saem direto
    // na impressora escolhida. Um agente parado aparece para o operador
    // exatamente como "só a comanda não sai, e sem erro nenhum" — sem este
    // registro, não há onde ver que ele nunca subiu.
    void announce(String acao, String motivo) => AppLogger.instance.info(
      'print_agent_role',
      data: {
        'acao': acao,
        'motivo': motivo,
        'modo': config?.mode.storageValue,
        'fase': current?.status.phase.name,
        'restaurante': restaurant,
      },
    );

    if (current == null || config == null) {
      announce('parado', 'rede local ainda iniciando');
      deviceAgent.stop();
      return;
    }
    if (config.mode == LocalTopologyMode.client) {
      announce('parado', 'terminal secundario: a fila da nuvem e do Principal');
      // O secundário imprime o que ele mesmo monta (recibo, comanda, nota de
      // pesagem) — isso não passa pelo agente. O que ele não faz é servir a
      // fila de `PrintJob` da nuvem, que é do principal.
      _rememberRole(principal: false);
      deviceAgent.stop();
      return;
    }
    if (current.status.phase == LocalTopologyPhase.starting) {
      announce('parado', 'aplicando configuracao da rede local');
      deviceAgent.stop();
      return;
    }
    if (restaurant.isEmpty) {
      // O agente não é derrubado aqui: ele sobe na próxima chamada de
      // [ensure], quando o bootstrap resolver o restaurante.
      announce('aguarda', 'restaurante ainda nao definido');
      return;
    }
    // Assumir a fila da nuvem vindo de outro papel não é a mesma coisa que
    // reiniciar já sendo o principal: no primeiro caso, o que está pendente
    // no servidor foi montado quando este terminal não era o dono da fila, e
    // pode já ter saído no papel em outro lugar. Ver
    // [LocalDeviceAgent.start] e [LocalPreferences.servedAsPrincipal].
    final takingOver = preferences != null && !preferences!.servedAsPrincipal;
    announce(
      'ativo',
      takingOver
          ? 'Caixa Principal assumindo a fila (papel anterior: outro)'
          : 'Caixa Principal com unidade definida',
    );
    deviceAgent.start(
      token: identity.accessToken,
      restaurantId: restaurant,
      takingOver: takingOver,
    );
    _rememberRole(principal: true);
  }

  /// Grava o papel com que este terminal está servindo a fila de impressão.
  ///
  /// Só quando ele muda: este método roda a cada notificação da rede local, e
  /// reescrever o arquivo de preferências em toda uma delas é ruído de disco
  /// sem nenhum ganho.
  void _rememberRole({required bool principal}) {
    final current = preferences;
    if (current == null || current.servedAsPrincipal == principal) return;
    unawaited(current.setServedAsPrincipal(principal));
  }

  Future<void> shutdown() async {
    _closed = true;
    final service = _service;
    _service = null;
    if (service == null) return;
    service.removeListener(_onServiceChanged);
    await service.shutdown();
  }

  @override
  void dispose() {
    unawaited(shutdown());
    super.dispose();
  }
}
