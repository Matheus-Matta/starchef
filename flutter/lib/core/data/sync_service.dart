import 'dart:async';

import '../logging/app_logger.dart';
import '../network/api_exception.dart';
import '../network/relay_origin.dart';
import 'entity_catalog.dart';
import 'fiscal_queue_service.dart';
import 'local_id.dart';
import 'offline_first_gateway.dart';
import 'sync_operation.dart';
import 'sync_queue_service.dart';

/// Transporte HTTP visto pelo serviço de sincronização.
///
/// Existe para que o [SyncService] não conheça `ApiClient` (que, por sua vez,
/// já depende do gateway) e para que os testes possam exercitar a fila sem
/// abrir socket nenhum.
abstract interface class SyncTransport {
  /// Executa a requisição de verdade contra o backend, sem passar pelo
  /// armazenamento local.
  Future<Map<String, dynamic>> send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? idempotencyKey,
    RelayOrigin? origin,
    void Function(RelayOrigin renewed)? onOriginRenewed,
  });

  /// O servidor responde agora? Consultado antes de gastar tentativas da fila.
  Future<bool> ping();
}

/// Falha temporária de rede — a operação volta para a fila (§23).
class TransientSyncFailure implements Exception {
  const TransientSyncFailure(
    this.message, {
    this.retryAfter,
    this.offline = true,
  });

  final String message;
  final Duration? retryAfter;
  final bool offline;

  @override
  String toString() => message;
}

enum SyncPhase { idle, syncing, offline, degraded, blocked }

class SyncSnapshot {
  const SyncSnapshot({
    required this.phase,
    this.pending = 0,
    this.failed = 0,
    this.fiscalPending = 0,
    this.fiscalBlocked = 0,
    this.lastError,
    this.nextRetryAt,
  });

  final SyncPhase phase;
  final int pending;
  final int failed;
  final int fiscalPending;

  /// Documentos que pararam e precisam de alguém: rejeição tributária,
  /// configuração fiscal inválida ou falha sem classificação. Esperar não
  /// resolve nenhum deles, então não podem se esconder em `fiscalPending`.
  final int fiscalBlocked;
  final String? lastError;
  final DateTime? nextRetryAt;

  bool get hasConnection =>
      phase == SyncPhase.idle ||
      phase == SyncPhase.syncing ||
      phase == SyncPhase.blocked;

  @override
  bool operator ==(Object other) =>
      other is SyncSnapshot &&
      phase == other.phase &&
      pending == other.pending &&
      failed == other.failed &&
      fiscalPending == other.fiscalPending &&
      fiscalBlocked == other.fiscalBlocked &&
      lastError == other.lastError &&
      nextRetryAt == other.nextRetryAt;

  @override
  int get hashCode => Object.hash(
    phase,
    pending,
    failed,
    fiscalPending,
    fiscalBlocked,
    lastError,
    nextRetryAt,
  );
}

/// Sincronização entre o SQLite local e o backend, nos dois sentidos.
///
/// **Saída**: drena a [SyncQueueService] em ordem, com backoff e distinção
/// entre erro temporário e erro que exige análise (§23).
///
/// **Entrada**: percorre as páginas da API de 20 em 20 (§13) e aplica os
/// registros como REMOTE, sem gerar operação de volta (§12). Quando existe
/// marca de tempo da última sincronização, usa `updated_after` para não
/// rebaixar a base inteira (§14).
///
/// Nada aqui bloqueia a interface: o serviço é acionado por timer, por
/// reconexão e por evento, sempre em segundo plano (§24).
class SyncService {
  SyncService({
    required this.gateway,
    required this.transport,
    this.pageSize = 20,
    this.pullInterval = const Duration(minutes: 5),
  });

  /// Quantas operações de saída por ciclo, para não monopolizar a rede.
  static const _maxOperationsPerCycle = 20;

  /// Teto de páginas por tipo em um único ciclo. Um catálogo gigante não pode
  /// prender o ciclo para sempre; o restante vem no ciclo seguinte.
  static const _maxPagesPerCycle = 50;

  /// Folga aplicada para trás na marca de tempo do delta sync (§14).
  static const clockSkewMargin = Duration(minutes: 2);

  final OfflineFirstGateway gateway;

  /// Para onde a fila entrega. No Caixa Principal é o backend; num Caixa
  /// Secundário é o próprio principal, pela rede local (§8). A troca acontece
  /// quando o terminal muda de papel em Configurações → Rede local.
  SyncTransport transport;

  final int pageSize;

  /// Com que frequência a cópia local é reconciliada com a origem.
  ///
  /// Não é `final` porque o intervalo certo depende do PAPEL do terminal, e o
  /// papel muda em Configurações sem reiniciar o app. Ver [usePullInterval].
  Duration pullInterval;

  /// Troca o destino da fila sem perder o que já está enfileirado.
  void useTransport(SyncTransport next) => transport = next;

  /// Cadência de reconciliação de um Caixa Secundário.
  ///
  /// O principal recebe as mudanças do salão pelo WebSocket da nuvem e as
  /// grava no SQLite dele na hora. O secundário não tem WebSocket nenhum —
  /// ele não fala com a nuvem — e nenhum canal do principal o avisa: tudo o
  /// que ele sabe vem do `pullAll` periódico. Com os 5 minutos padrão, a
  /// comanda que o garçom acabou de lançar levava até 5 minutos para
  /// aparecer no segundo caixa, e quem fechasse a conta nesse intervalo
  /// fechava sem os últimos itens na tela. Trinta segundos numa chamada de
  /// rede local, incremental e paginada, é barato.
  static const secondaryPullInterval = Duration(seconds: 30);

  /// Troca a cadência do `pullAll` e, se o serviço já estiver rodando,
  /// reprograma o temporizador na hora.
  void usePullInterval(Duration next) {
    if (next == pullInterval) return;
    pullInterval = next;
    if (_pullTimer != null && !_disposed) {
      _pullTimer?.cancel();
      _pullTimer = Timer.periodic(pullInterval, (_) => unawaited(pullAll()));
    }
  }

  final _snapshotController = StreamController<SyncSnapshot>.broadcast();
  Stream<SyncSnapshot> get snapshots => _snapshotController.stream;

  SyncSnapshot _snapshot = const SyncSnapshot(phase: SyncPhase.idle);
  SyncSnapshot get snapshot => _snapshot;

  Timer? _pushTimer;
  Timer? _pullTimer;
  Timer? _fiscalTimer;

  /// Ciclo de entrega em andamento, se houver. Concorrentes esperam ESTE
  /// mesmo `Future` em vez de simplesmente desistir — era isso que fazia
  /// `flushSalesQueue` (chamado no gesto de concluir o pedido, para o
  /// recebimento chegar ao servidor ANTES da emissão fiscal) virar um no-op
  /// silencioso sempre que um ciclo periódico (dos 450 ms de debounce de uma
  /// escrita anterior — fechar o pedido, por exemplo) ainda estava em voo: o
  /// recebimento ficava na fila, a nota emitia sem ele, e só o recibo saía.
  Future<void>? _pushCycle;

  /// Chegou trabalho novo enquanto um ciclo já rodava — o ciclo atual não vai
  /// vê-lo, então mais uma volta é necessária antes de dar por concluído.
  bool _pushAgain = false;

  /// Um `push(force: true)` pediu para pular a checagem de conectividade e a
  /// próxima volta ainda não começou. Existe para o "tentar agora" (§ push)
  /// não se perder quando chega enquanto outro ciclo já está em voo — sem
  /// isto, ele só reaproveitaria o ciclo alheio via `_pushAgain` e a volta
  /// extra voltaria a adivinhar a conexão como um ciclo automático qualquer.
  bool _forceNextPush = false;
  bool _pulling = false;
  bool _disposed = false;

  /// Inicia os ciclos periódicos. A interface não espera por nenhum deles.
  void start() {
    if (_disposed) return;
    _pullTimer?.cancel();
    _pullTimer = Timer.periodic(pullInterval, (_) => unawaited(pullAll()));
    // A fila fiscal tem cadência própria (§16): uma nota recusada pela SEFAZ
    // não pode segurar a sincronização das vendas, e insistir de segundo em
    // segundo só geraria rejeição por excesso de consultas.
    _fiscalTimer?.cancel();
    _fiscalTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => unawaited(pushFiscal()),
    );
    schedulePush();
  }

  void stop() {
    _pushTimer?.cancel();
    _pushTimer = null;
    _pullTimer?.cancel();
    _pullTimer = null;
    _fiscalTimer?.cancel();
    _fiscalTimer = null;
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    stop();
    await _snapshotController.close();
  }

  /// Agenda uma drenagem da fila, agrupando chamadas próximas.
  void schedulePush({Duration delay = const Duration(milliseconds: 450)}) {
    if (_disposed || gateway.scope == null) return;
    _pushTimer?.cancel();
    _pushTimer = Timer(delay, () => unawaited(push()));
  }

  /// Antecipa tudo: usado pelo botão "sincronizar agora" e pela reconexão.
  Future<void> syncNow() async {
    final scope = gateway.scope;
    if (scope == null) return;
    await gateway.queue.retryAllNow(scope: scope);
    // "Agora" é literal: quem chamou (o diálogo de revisão da fila) já está
    // olhando para o problema e pediu para tentar na hora — a resposta certa
    // é uma tentativa real, não confiar em o WebSocket já ter percebido a
    // volta do servidor.
    await push(force: true);
    await pushFiscal();
    await pullAll(force: true);
  }

  // ------------------------------------------------------------------ saída

  /// Entrega as operações pendentes ao backend, em ordem (§6).
  ///
  /// Reentrante: uma chamada que chega com outra já em voo NÃO desiste — ela
  /// marca que precisa de mais uma volta e espera o mesmo ciclo terminar.
  /// Sem isso, quem precisa da GARANTIA de entrega (como o "Concluir pedido"
  /// esperando o recebimento chegar antes de emitir a nota) podia receber de
  /// volta um retorno vazio sem ter entregado nada.
  Future<void> push({bool force = false}) {
    if (_disposed || gateway.scope == null) return Future.value();
    if (force) _forceNextPush = true;
    final inFlight = _pushCycle;
    if (inFlight != null) {
      _pushAgain = true;
      return inFlight;
    }
    final cycle = _runPushCycles();
    _pushCycle = cycle;
    return cycle;
  }

  Future<void> _runPushCycles() async {
    try {
      do {
        _pushAgain = false;
        final force = _forceNextPush;
        _forceNextPush = false;
        await _pushOnce(force: force);
      } while (_pushAgain && !_disposed);
    } finally {
      _pushCycle = null;
    }
  }

  Future<void> _pushOnce({bool force = false}) async {
    final scope = gateway.scope;
    if (_disposed || scope == null) return;
    var summary = await gateway.queue.summary(scope: scope);
    if (!summary.hasWork) {
      await _publish(summary.failed > 0 ? SyncPhase.blocked : SyncPhase.idle);
      return;
    }

    // Confirma que o servidor responde antes de gastar tentativas: sem
    // isso, um ciclo com a rede caída levaria o backoff de cada operação ao
    // teto sem nenhuma chance real de entrega. Falando direto com a nuvem
    // (Caixa Principal ou terminal sozinho), quem responde por isso é o
    // WebSocket do próprio terminal (`ApiClient.isRealtimeConnected`), não um
    // `GET /health/` à parte — ver `ApiClient.notifyRealtimeConnected`. Num
    // Caixa Secundário, `ping()` é o `probe()` local contra o Principal (§8),
    // que continua HTTP porque é rede local, não a nuvem.
    if (!force && !_snapshot.hasConnection && !await transport.ping()) {
      await _publish(
        SyncPhase.offline,
        error: 'O servidor não respondeu à verificação de saúde.',
      );
      _scheduleRetryAfter(SyncQueueService.retryLadder.first);
      return;
    }

    await _publish(SyncPhase.syncing);
    var processed = 0;
    // A fila tem trabalho e não conseguiu mover NADA? Isso é diferente de
    // "acabou": alguma operação está esperando por algo que talvez não venha.
    var starved = false;
    while (processed < _maxOperationsPerCycle) {
      final claimed = await gateway.queue.claimNext(scope: scope);
      if (claimed == null) {
        starved = processed == 0;
        break;
      }
      final entry = await gateway.queue.resolveReferences(
        claimed,
        scope: scope,
      );
      final delivered = await _deliver(entry, scope: scope);
      if (!delivered) break;
      processed += 1;
    }

    // Uma espera legítima (a criação ainda vai subir) se resolve sozinha na
    // próxima volta. Uma espera por um lançamento que não está mais na fila
    // não se resolve nunca — e ficava assim, invisível: sem tentativa, sem
    // erro, sem botão na tela de revisão, segurando o fechamento e o
    // pagamento atrás dela.
    if (starved) {
      final stranded = await gateway.queue.failStrandedDependencies(
        scope: scope,
      );
      for (final entry in stranded) {
        AppLogger.instance.warning(
          'sync_operacao_encalhada',
          data: {
            'operation_id': entry.operationId,
            'path': entry.path,
            'causa': entry.lastError,
          },
        );
      }
    }

    summary = await gateway.queue.summary(scope: scope);
    if (summary.failed > 0) {
      await _publish(SyncPhase.blocked, error: 'Há operações para revisar.');
    } else if (summary.pending > 0) {
      schedulePush(delay: const Duration(seconds: 1));
    } else {
      await _publish(SyncPhase.idle);
    }
  }

  /// Entrega uma operação. Devolve `false` quando o ciclo deve parar.
  Future<bool> _deliver(SyncQueueEntry entry, {required String scope}) async {
    try {
      final response = await transport.send(
        entry.method,
        entry.path,
        query: entry.query,
        body: entry.payload,
        // A chave de idempotência acompanha TODA tentativa da mesma operação
        // (§7): se o servidor processou antes de a resposta se perder, o
        // reenvio devolve a resposta original em vez de duplicar a venda.
        idempotencyKey: entry.operationId,
        // A fila deste terminal entrega também o que outros caixas
        // originaram, e cada operação sobe no nome de quem a criou.
        origin: entry.origin,
        // Token do secundário renovado aqui: fica gravado para as próximas
        // tentativas não renovarem de novo.
        onOriginRenewed: (renewed) =>
            unawaited(gateway.queue.updateOrigin(entry.id, renewed)),
      );
      await gateway.confirmDelivery(entry, response);
      await gateway.queue.markSynced(entry.id);
      return true;
    } on TransientSyncFailure catch (error) {
      final attempts = entry.attempts + 1;
      final nextRetryAt = await gateway.queue.markRetry(
        entry.id,
        attempts: attempts,
        error: error.message,
        serverDelay: error.retryAfter,
      );
      await _publish(
        error.offline ? SyncPhase.offline : SyncPhase.degraded,
        error: error.message,
        nextRetryAt: nextRetryAt,
      );
      _scheduleRetryAfter(nextRetryAt.difference(DateTime.now().toUtc()));
      // Mesmo que a conexão deste envio tenha caído, outras operações podem
      // usar outro relay/origem e continuar. Esta sai da vez até o backoff.
      return true;
    } on ApiException catch (error) {
      // Sessão vencida não é recusa de negócio. O `ApiClient` já tentou
      // renovar o token uma vez; se a renovação falhou por falta de rede,
      // marcar a operação como recusada mandaria a fila inteira para revisão
      // manual por causa de uma oscilação. Ela espera e tenta de novo.
      if (error.statusCode == 401) {
        final attempts = entry.attempts + 1;
        final nextRetryAt = await gateway.queue.markRetry(
          entry.id,
          attempts: attempts,
          error: error.message,
        );
        await _publish(
          SyncPhase.degraded,
          error: 'Sessão expirada. Entre novamente para retomar o envio.',
          nextRetryAt: nextRetryAt,
        );
        // Outra operação pode pertencer a outro operador/origem e possuir uma
        // sessão válida. O item atual entra em backoff sem bloquear a fila.
        return true;
      }
      // Divergência de total no fechamento é a exceção: o servidor recusou
      // conferindo um número que só este terminal calculou. Reenviar sem o
      // `expected_total` deixa o total autoritativo valer, em vez de prender a
      // venda — e o pagamento, que espera atrás dela — numa revisão manual que
      // o operador não tem como fazer.
      if (_isCloseTotalDivergence(entry, error) &&
          await gateway.queue.requeueCloseIgnoringExpectedTotal(entry.id)) {
        AppLogger.instance.warning(
          'sync_fechamento_total_reconciliado',
          data: {
            'operation_id': entry.operationId,
            'path': entry.path,
            'expected_total': '${entry.payload?['expected_total']}',
            'causa': error.message,
          },
        );
        await _publish(SyncPhase.syncing, error: error.message);
        return true;
      }
      // Recusa de negócio: reenviar repetiria a rejeição para sempre. Sai da
      // rotação e vira uma pendência visível — sem travar as vendas seguintes,
      // que o `claimNext` continua entregando.
      await gateway.queue.markFailed(entry.id, error: error.message);
      await gateway.markDeliveryFailed(entry);
      AppLogger.instance.warning(
        'sync_operacao_recusada',
        data: {
          'operation_id': entry.operationId,
          'path': entry.path,
          'status': error.statusCode,
        },
      );
      await _publish(SyncPhase.blocked, error: error.message);
      return true;
    } catch (error, stack) {
      // QUALQUER outra exceção. Sem este ramo, uma só operação derrubava o
      // ciclo inteiro: `FormatException` do `jsonDecode` quando um proxy
      // reverso caído devolve HTML no lugar do JSON, `TypeError` de um payload
      // com formato inesperado, ou um erro dentro de `confirmDelivery` — e a
      // exceção subia por `push()`, parando a sincronização do terminal com a
      // fila cheia e nenhum aviso na tela.
      //
      // Tratada como falha TEMPORÁRIA de propósito: a causa provável é do
      // outro lado (proxy, deploy no meio, resposta truncada) e some sozinha.
      // A escada de retentativa não desiste (o teto de 5 min se repete): uma
      // venda não pode ser descartada porque o servidor respondeu lixo. O
      // que insiste fica visível no badge como "Instável", com o motivo na
      // tela de revisão — e o `last_error` diz exatamente o que veio.
      final attempts = entry.attempts + 1;
      final nextRetryAt = await gateway.queue.markRetry(
        entry.id,
        attempts: attempts,
        error: 'Resposta inesperada do servidor: $error',
      );
      AppLogger.instance.error(
        'sync_resposta_inesperada',
        data: {
          'operation_id': entry.operationId,
          'path': entry.path,
          'erro': '$error',
        },
        stackTrace: stack,
      );
      await _publish(
        SyncPhase.degraded,
        error: 'O servidor respondeu de forma inesperada. Tentando de novo.',
        nextRetryAt: nextRetryAt,
      );
      _scheduleRetryAfter(nextRetryAt.difference(DateTime.now().toUtc()));
      return true;
    }
  }

  /// O servidor recusou este fechamento só porque o total conferido não bate?
  ///
  /// A checagem exige as duas coisas: um fechamento que ainda carrega o total
  /// calculado aqui, e uma recusa que fala do total. Uma recusa por outro
  /// motivo (desconto sem permissão de gerente, pedido bloqueado) continua
  /// indo para a revisão, onde é o lugar dela.
  static bool _isCloseTotalDivergence(SyncQueueEntry entry, ApiException error) {
    if (error.statusCode != 400) return false;
    if (!entry.path.endsWith('/close/')) return false;
    if (entry.payload?['expected_total'] == null) return false;
    return error.message.toLowerCase().contains('total');
  }

  // ---------------------------------------------------------------- entrada

  /// Intervalo mínimo entre duas cargas completas do catálogo.
  ///
  /// Uma carga completa são ~20 leituras paginadas — o catálogo inteiro da
  /// loja. Ela existe para o terminal nascer com tudo em mãos e para cobrir o
  /// que o WebSocket possa ter perdido; nada nela precisa acontecer duas vezes
  /// no mesmo minuto.
  static const minimumFullPullInterval = Duration(minutes: 2);

  DateTime? _lastFullPullAt;
  String? _lastFullPullRestaurant;

  /// Baixa todos os tipos do catálogo, do mais essencial ao menos (§24).
  ///
  /// [force] ignora o intervalo mínimo — é o "sincronizar agora", em que
  /// alguém está olhando e pediu.
  ///
  /// A recarga da tela (`_load`) termina disparando esta carga, e ela é
  /// disparada de novo a cada sinal do WebSocket, a cada venda concluída, a
  /// cada refresh manual. Sem freio, uma loja movimentada mandava o catálogo
  /// inteiro à API várias vezes por minuto, estourava o limite de requisições
  /// da conta e derrubava junto o que importava de verdade: o `/close/` e o
  /// `/pay/` da venda seguinte, recusados com "Pedido foi limitado". Pior, o
  /// 429 derrubava o WebSocket, cuja reconexão dispara os sinais que pedem
  /// outra recarga — a espiral se alimentava sozinha.
  Future<void> pullAll({String? restaurantId, bool force = false}) async {
    if (_disposed || _pulling || gateway.scope == null) return;
    final last = _lastFullPullAt;
    final sameRestaurant = _lastFullPullRestaurant == restaurantId;
    if (!force &&
        last != null &&
        sameRestaurant &&
        DateTime.now().difference(last) < minimumFullPullInterval) {
      return;
    }
    _pulling = true;
    _lastFullPullAt = DateTime.now();
    _lastFullPullRestaurant = restaurantId;
    try {
      for (final descriptor in gateway.pullOrder) {
        try {
          await pull(descriptor, restaurantId: restaurantId);
        } catch (error) {
          // Um recurso com resposta inesperada não pode impedir a carga dos
          // outros: sem isto, um erro no cardápio deixava o caixa sem
          // impressoras, sem mesas e sem formas de pagamento.
          AppLogger.instance.warning(
            'sync_tipo_falhou',
            data: {'entity_type': descriptor.type, 'causa': '$error'},
          );
        }
      }
      // A versão que acabou de chegar do servidor pode trazer de volta uma
      // comanda ocupada por uma venda que este terminal já concluiu — o `pay`
      // dela ainda está na fila, então lá ela segue aberta. Reaplicar a
      // liberação aqui evita que a sincronização re-trave a comanda que o
      // operador precisa entregar ao próximo cliente.
      try {
        final released = await gateway.releaseSettledCommands();
        if (released > 0) {
          AppLogger.instance.info(
            'comandas_liberadas_localmente',
            data: {'quantidade': released},
          );
        }
      } catch (error) {
        AppLogger.instance.warning(
          'comandas_liberacao_falhou',
          data: {'causa': '$error'},
        );
      }
    } finally {
      _pulling = false;
    }
  }

  /// Baixa um tipo, paginando de [pageSize] em [pageSize] (§13).
  ///
  /// Quando já houve sincronização anterior, pede só o que mudou desde então
  /// (§14) — é o que evita rebaixar o cardápio inteiro a cada reconexão.
  Future<int> pull(
    EntityDescriptor descriptor, {
    String? restaurantId,
    bool full = false,
  }) async {
    final scope = gateway.scope;
    if (scope == null) return 0;
    final since = full ? null : await gateway.lastSyncAt(descriptor.type);
    final restaurant = restaurantId ?? gateway.restaurantId;
    final startedAt = DateTime.now().toUtc();

    var page = 1;
    var applied = 0;
    var completed = false;
    while (page <= _maxPagesPerCycle) {
      final Map<String, dynamic> response;
      try {
        response = await transport.send(
          'GET',
          descriptor.collectionPath,
          query: {
            'page': page,
            'page_size': pageSize,
            if (restaurant != null &&
                restaurant.isNotEmpty &&
                descriptor.restaurantField != null)
              descriptor.restaurantField!: restaurant,
            if (since != null) ...{
              'updated_after': since.toIso8601String(),
              // Sem isto, uma exclusão feita na retaguarda nunca chegaria ao
              // caixa offline: o registro simplesmente sumiria da listagem e a
              // cópia local continuaria vendável.
              'include_deleted': 1,
            },
          },
        );
      } on TransientSyncFailure catch (error) {
        await gateway.recordSync(
          descriptor.type,
          at: null,
          error: error.message,
        );
        await _publish(SyncPhase.offline, error: error.message);
        return applied;
      } on ApiException catch (error) {
        // Um recurso que esta conta não pode ler (403) ou que este backend não
        // publica (404) não pode interromper a carga dos outros.
        await gateway.recordSync(
          descriptor.type,
          at: null,
          error: error.message,
        );
        return applied;
      }

      applied += await gateway.applyRemoteCollection(
        descriptor.collectionPath,
        response,
      );

      final results = response['results'];
      final count = results is List ? results.length : 0;
      // Página vazia ou sem `next`: acabou. Nunca repetir a página anterior
      // nem inventar registros que não existem (§13).
      if (count == 0 || response['next'] == null || count < pageSize) {
        completed = true;
        break;
      }
      page += 1;
    }

    // A marca de tempo só avança quando a carga chegou ao fim. Se o ciclo
    // parou no teto de páginas, gravar aqui faria a próxima carga pedir
    // `updated_after` a partir de agora e pular tudo o que ficou para trás.
    if (!completed) return applied;

    // Uma margem para trás cobre a diferença de relógio entre o terminal e o
    // servidor: `updated_after` é exclusivo, e alguns segundos de diferença
    // bastariam para um registro nunca descer. Reaplicar alguns registros é
    // barato e idempotente; perder um não é.
    await gateway.recordSync(
      descriptor.type,
      at: startedAt.subtract(clockSkewMargin),
    );
    return applied;
  }

  /// Reconciliação pontual de um recurso avisado pelo WebSocket (§11).
  ///
  /// O evento do backend carrega apenas metadados (`resource`, `action`,
  /// `id`), então o registro é lido e **persistido no SQLite** — não apenas
  /// jogado na memória da tela.
  Future<bool> pullEntity({
    required String entityType,
    required String entityId,
    required bool deleted,
  }) async {
    final descriptor = EntityCatalog.byType(entityType);
    if (descriptor == null || gateway.scope == null || entityId.isEmpty) {
      return false;
    }
    final repo = gateway.repository(entityType);
    if (deleted) {
      await repo.markRemoteDeleted(entityId);
      return true;
    }
    try {
      final response = await transport.send(
        'GET',
        descriptor.detailPath(entityId),
      );
      await repo.applyRemote(response);
      return true;
    } on TransientSyncFailure {
      // A reconciliação completa do próximo ciclo cobre o que se perdeu aqui.
      return false;
    } on ApiException catch (error) {
      if (error.statusCode == 404) {
        await repo.markRemoteDeleted(entityId);
        return true;
      }
      return false;
    }
  }

  // ----------------------------------------------------------------- fiscal

  /// Tenta emitir os documentos fiscais pendentes (§16).
  ///
  /// Roda separado da fila de vendas de propósito: uma nota recusada pela
  /// SEFAZ não pode segurar a sincronização de um pedido.
  ///
  /// A resposta é LIDA, não presumida. Antes, qualquer HTTP bem-sucedido virava
  /// `AUTHORIZED` aqui — inclusive `{"emitted": false}`, que é exatamente o
  /// servidor dizendo que a nota não saiu, e inclusive uma nota que ficou
  /// aguardando autorização. O caixa via "nota autorizada" nos três casos.
  /// `orderId` entrega a nota DAQUELE pedido, furando a ordem da fila —
  /// e o caso do operador esperando o cupom fiscal no balcao.
  Future<void> pushFiscal({
    String emitPath = '/invoices/emit/',
    String? orderId,
  }) async {
    final scope = gateway.scope;
    if (scope == null) return;
    final document = orderId == null
        ? await gateway.fiscalQueue.claimNext(scope: scope)
        : await gateway.fiscalQueue.claimForOrder(
            scope: scope,
            orderId: orderId,
          );
    if (document == null) return;
    final attempts = document.attempts + 1;
    try {
      final response = await transport.send(
        'POST',
        emitPath,
        body: document.payload,
        idempotencyKey: document.documentId,
      );
      final status = FiscalStatus.fromResponse(response);
      await gateway.fiscalQueue.applyOutcome(
        document.id,
        status: status,
        attempts: attempts,
        response: response,
        error: status.hasFiscalDocument
            ? null
            : '${response['error_message'] ?? response['message'] ?? ''}',
      );
    } on TransientSyncFailure catch (error) {
      await gateway.fiscalQueue.markRetry(
        document.id,
        attempts: attempts,
        error: error.message,
        serverDelay: error.retryAfter,
      );
    } on ApiException catch (error) {
      // Um 5xx ou um 429 não dizem nada sobre a nota: são o servidor fora do
      // ar, e desistir aqui deixaria uma venda paga sem documento fiscal para
      // sempre. Só uma recusa do próprio servidor encerra a tentativa.
      final code = error.statusCode ?? 0;
      if (error.isConnectivity || code == 429 || code >= 500) {
        // O prazo do PRÓPRIO 429/503 (`Retry-After`, reconstruído na
        // travessia do relay) prevalece sobre a escada interna — repetir
        // antes do prazo pedido é o que mantinha a janela de limite sempre
        // quente, inclusive para outros terminais da mesma conta.
        await gateway.fiscalQueue.markRetry(
          document.id,
          attempts: attempts,
          error: error.message,
          serverDelay: error.retryAfter,
        );
        return;
      }
      await gateway.fiscalQueue.markFailed(
        document.id,
        error: error.message,
        status: code == 401 || code == 403
            ? FiscalStatus.configurationError
            : FiscalStatus.rejected,
      );
    }
  }

  // ------------------------------------------------------------------ apoio

  void _scheduleRetryAfter(Duration delay) {
    if (_disposed) return;
    final safe = delay.isNegative ? SyncQueueService.retryLadder.first : delay;
    schedulePush(delay: safe);
  }

  Future<void> _publish(
    SyncPhase phase, {
    String? error,
    DateTime? nextRetryAt,
  }) async {
    final scope = gateway.scope;
    if (scope == null || _disposed) return;
    final summary = await gateway.queue.summary(scope: scope);
    final fiscalPending = await gateway.fiscalQueue.pendingCount(scope: scope);
    final fiscalBlocked = await gateway.fiscalQueue.blockedCount(scope: scope);
    final effective = summary.failed > 0 && phase == SyncPhase.idle
        ? SyncPhase.blocked
        : phase;
    final next = SyncSnapshot(
      phase: effective,
      pending: summary.pending + summary.processing,
      failed: summary.failed,
      fiscalPending: fiscalPending,
      fiscalBlocked: fiscalBlocked,
      lastError: error,
      nextRetryAt: nextRetryAt,
    );
    if (next == _snapshot) return;
    _snapshot = next;
    if (!_snapshotController.isClosed) _snapshotController.add(next);
  }

  /// Operação que ainda referencia um ID temporário — exposto para
  /// diagnóstico da tela de revisão da fila.
  static bool dependsOnUnsyncedCreation(SyncQueueEntry entry) =>
      LocalId.isTemporary(entry.entityId) ||
      entry.path.contains(LocalId.temporaryPrefix);
}
