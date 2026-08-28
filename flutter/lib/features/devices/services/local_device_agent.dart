import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/network/realtime_client.dart';
import '../../../core/data/print_queue_service.dart';
import '../../../core/storage/local_preferences.dart';
import '../domain/printer_endpoint.dart';
import '../printing/print_document.dart';
import '../printing/printer.dart';
import '../printing/printer_device.dart';
import '../printing/printer_transport.dart';
import 'print_template_cache.dart';

export '../printing/print_document.dart';
export '../printing/printer.dart';
export '../printing/printer_device.dart';
export '../printing/printer_transport.dart'
    show PrinterCommunicationException, PrintTiming;

/// Agente local de impressão do processo principal.
///
/// Ele cuida do **fluxo** de impressão: trazer trabalhos do servidor, guardá-los
/// na fila local, girar essa fila e confirmar o que já saiu no papel. Falar com
/// o equipamento não é mais tarefa dele — quem faz isso é [Printer] e suas
/// subclasses (`../printing/`), usadas por igual aqui, no cadastro de
/// impressoras, na Balança Rápida e no relay. Antes esta classe acumulava as
/// duas coisas, e mexer no corte do papel exigia entender o WebSocket.
///
/// A leitura da balança **não** passa por aqui: quem lê o equipamento é a
/// própria janela que vai usá-lo, abrindo a porta serial diretamente
/// ([SerialScaleReader]). Isso eliminou o lease remoto (`claim-agent`) e a
/// consulta periódica de peso pela API.
///
/// A fila de impressão não é varrida por polling: o backend já publica
/// `model.updated`/`model.created` para qualquer `PrintJob` da conta em
/// `/ws/pdv/<restaurant_id>/` (todo `TenantModel` ganha isso de graça — ver
/// `apps/realtime/signals.py`). O agente assina esse evento e só consulta
/// `/print-jobs/` quando um deles chega, mais uma verificação pontual ao
/// conectar/reconectar o WS, para cobrir o que foi perdido enquanto a conexão
/// estava caída. Modelos de impressão seguem a mesma regra: sem timer,
/// sincroniza no início e a cada reconexão.
class LocalDeviceAgent {
  LocalDeviceAgent({
    required this.api,
    this.preferences,
    Future<bool> Function(PrinterEndpoint target)? availabilityProbe,
    Future<void> Function(Duration duration)? delay,
    Future<void> Function(PrinterEndpoint target, List<int> bytes)?
    networkWriter,
    this.cutDelay = const Duration(milliseconds: 350),
    this.postCutSettleDelay = const Duration(milliseconds: 400),
  }) : _availabilityProbe = availabilityProbe,
       _networkWriter = networkWriter,
       _delay = delay ?? Future<void>.delayed;

  final ApiClient api;
  final LocalPreferences? preferences;
  final Future<bool> Function(PrinterEndpoint target)? _availabilityProbe;
  final Future<void> Function(PrinterEndpoint target, List<int> bytes)?
  _networkWriter;
  final Future<void> Function(Duration duration) _delay;

  /// Ver [PrintTiming.cutDelay].
  final Duration cutDelay;

  /// Ver [PrintTiming.postCutSettleDelay].
  final Duration postCutSettleDelay;

  final ValueNotifier<PrinterAvailability> printerAvailability =
      ValueNotifier<PrinterAvailability>(PrinterAvailability.checking);

  /// Dependências que toda impressora deste terminal recebe.
  ///
  /// Quem for imprimir em qualquer tela constrói a impressora com isto —
  /// `KitchenPrinter(device, runtime: agent.printing)` — e ganha as mesmas
  /// pausas físicas e a mesma publicação de status da tela de vendas.
  late final PrinterRuntime printing = PrinterRuntime(
    timing: PrintTiming(
      cutDelay: cutDelay,
      postCutSettleDelay: postCutSettleDelay,
      delay: _delay,
    ),
    networkWriter: _networkWriter,
    availabilityProbe: _availabilityProbe,
    onStatus: (status) => printerAvailability.value = status,
  );

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
  Timer? _availabilityTimer;
  Timer? _scheduledPrintTimer;

  Timer? _printJobsPollTimer;

  /// Ritmo próprio da fila local: ela precisa girar mesmo sem rede, senão um
  /// cupom que falhou por falta de papel só sairia no próximo evento do
  /// WebSocket — que, offline, nunca chega.
  Timer? _printQueueTimer;

  /// Só um giro da fila por vez.
  ///
  /// O timer da fila, o evento do WebSocket e um cupom montado agora na tela
  /// disparavam três drenagens simultâneas, e as três mandavam papel para a
  /// mesma impressora ao mesmo tempo. A reserva do equipamento em
  /// [Printer.send] impede o atropelo físico; esta trava evita a disputa
  /// antes dela, no processo que já sabe que está imprimindo.
  Future<void>? _drainInFlight;

  /// O agente está em operação neste terminal?
  ///
  /// Quem imprime **automaticamente** é ele: a comanda de cozinha do backend
  /// chega como `PrintJob` e é ele quem consulta e imprime. Recibo e nota de
  /// teste saem por outro caminho (direto na impressora escolhida), então um
  /// agente parado se manifesta exatamente assim: "só a comanda de pedido
  /// novo não sai, e não aparece erro nenhum".
  bool get isRunning => _token != null && _restaurantId != null;

  void start({required String token, required String restaurantId}) {
    if (_realtime != null && _token == token && _restaurantId == restaurantId) {
      return;
    }
    AppLogger.instance.info(
      'print_agent_start',
      data: {'restaurante': restaurantId, 'reinicio': _realtime != null},
    );
    _token = token;
    _restaurantId = restaurantId;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _backoffUntil = null;
    _availabilityTimer?.cancel();
    _scheduledPrintTimer?.cancel();
    _scheduledPrintTimer = null;
    _printJobsPollTimer?.cancel();
    printerAvailability.value = PrinterAvailability.checking;
    unawaited(refreshPrinterAvailability());
    _availabilityTimer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => unawaited(refreshPrinterAvailability(useCachedDevices: true)),
    );
    // Rede de segurança independente do WS: o evento em tempo real que
    // liberaria a rodada da cozinha pode se perder numa reconexão, e sem
    // isto a impressão automática ficava sem nenhum outro gatilho até o
    // operador tocar em alguma tela que reconsultasse `/print-jobs/` por
    // conta própria.
    _printJobsPollTimer = Timer.periodic(
      const Duration(minutes: 2),
      (_) => unawaited(_guarded(_processPrintJobs)),
    );
    // A fila local gira sozinha, com ou sem rede. É o que faz um cupom que
    // falhou por falta de papel sair assim que o papel volta, sem depender de
    // um evento do servidor que, offline, nunca chega.
    _printQueueTimer?.cancel();
    _printQueueTimer = Timer.periodic(
      const Duration(seconds: 20),
      (_) => unawaited(drainPrintQueue()),
    );
    _stopRealtime();
    final realtime = RealtimeClient(
      urlBuilder: () => api.pdvSocketUrl(_restaurantId!),
      headersBuilder: () => {
        'Authorization': 'Bearer ${api.currentAccessToken ?? _token!}',
      },
    );
    _realtime = realtime;
    // Ao (re)conectar, uma verificação pontual cobre o que pode ter mudado
    // enquanto a conexão estava caída — nunca um timer recorrente.
    _connectedSubscription = realtime.onConnected.listen((_) => _onConnected());
    _eventSubscription = realtime.events.listen(_onRealtimeEvent);
    realtime.start();
  }

  void stop() {
    if (_token != null || _restaurantId != null) {
      AppLogger.instance.info(
        'print_agent_stop',
        data: {'restaurante': _restaurantId},
      );
    }
    _stopRealtime();
    _availabilityTimer?.cancel();
    _availabilityTimer = null;
    _scheduledPrintTimer?.cancel();
    _scheduledPrintTimer = null;
    _printJobsPollTimer?.cancel();
    _printJobsPollTimer = null;
    _printQueueTimer?.cancel();
    _printQueueTimer = null;
    _token = null;
    _restaurantId = null;
    _lastTemplateSync = null;
    _lastDeviceSync = null;
    _backoffUntil = null;
    _deviceSyncInFlight = null;
    _printers = const [];
    printerAvailability.value = PrinterAvailability.notConfigured;
  }

  void dispose() {
    stop();
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

  static bool isDeviceConfigurationEvent(
    RealtimeEvent event,
    String? restaurantId,
  ) {
    final resource = '${event.payload['resource'] ?? ''}';
    if (resource != 'printers.printer' && resource != 'printers.scale') {
      return false;
    }
    final eventRestaurantId = '${event.payload['restaurant_id'] ?? ''}';
    return eventRestaurantId.isEmpty || eventRestaurantId == restaurantId;
  }

  void _onRealtimeEvent(RealtimeEvent event) {
    final restaurantId = _restaurantId;
    if (restaurantId == null) return;
    api.applyRealtimeEvent(event, restaurantId: restaurantId);
    if (event.payload['resource'] == 'printers.printjob') {
      // Loga mesmo quando o restaurante não bate: um evento chegando com o
      // restaurant_id errado (ou vazio, quando não deveria estar) explicaria
      // a impressão nunca disparar sem nenhum erro visível na tela.
      AppLogger.instance.info(
        'realtime_printjob_event',
        data: {
          'event_restaurant': event.payload['restaurant_id'],
          'agent_restaurant': restaurantId,
          'matched': isPrintJobEvent(event, restaurantId),
        },
      );
    }
    if (isPrintJobEvent(event, restaurantId)) {
      unawaited(_onPrintJobEvent());
    }
    if (isDeviceConfigurationEvent(event, restaurantId)) {
      _lastDeviceSync = null;
      unawaited(
        _guarded(() async {
          await _syncDevicesIfNeeded();
          await refreshPrinterAvailability(useCachedDevices: true);
        }),
      );
    }
  }

  Future<void> _onConnected() {
    api.notifyRealtimeConnected();
    return _guarded(() {
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
  }

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

  /// Roda um ciclo de `_processPrintJobs` sem passar por `start()` (que abre
  /// o WebSocket e os timers reais). Só para teste.
  @visibleForTesting
  Future<void> processPendingPrintJobsForTesting({
    required String token,
    required String restaurantId,
  }) {
    _token = token;
    _restaurantId = restaurantId;
    return _processPrintJobs();
  }

  /// Ciclo completo da impressão: buscar o que o servidor tem, colocar na
  /// fila **local** e imprimir dela.
  ///
  /// A separação é o ponto. Antes, buscar e imprimir eram a mesma coisa, e por
  /// isso a impressão dependia da rede: com a internet fora não havia o que
  /// buscar — e nada saía no papel, nem um cupom montado aqui mesmo. Agora a
  /// busca é opcional e a impressão é local.
  Future<void> _processPrintJobs() async {
    _scheduledPrintTimer?.cancel();
    _scheduledPrintTimer = null;
    await _syncDevicesIfNeeded();
    await _ingestRemotePrintJobs();
    await drainPrintQueue();
    await _confirmPrintedJobs();
  }

  /// Fila local deste terminal, quando o armazenamento operacional já está
  /// vinculado a uma sessão.
  ///
  /// Pública porque a tela da fila lê e opera sobre ela: é o mesmo objeto que
  /// o agente drena, e não uma segunda visão do mesmo banco.
  PrintQueueService? get printQueue => api.localStore?.printQueue;

  String? get printScope => api.localStore?.scope;

  PrintQueueService? get _printQueue => printQueue;

  String? get _printScope => printScope;

  /// Traz os trabalhos do servidor para a fila local, sem imprimir.
  ///
  /// Uma falha aqui significa apenas "não há novidade do servidor": o que já
  /// está na fila continua saindo normalmente.
  Future<void> _ingestRemotePrintJobs() async {
    final queue = _printQueue;
    final scope = _printScope;
    final availablePrinters = <String, Map<String, dynamic>>{
      for (final printer in _printers)
        if (PrinterDevice.fromJson(printer).isAddressable)
          '${printer['id']}': printer,
    };

    DateTime? nextScheduledAt;
    var ingested = 0;
    for (final status in ['scheduled', 'pending', 'rendered']) {
      final List<Map<String, dynamic>> jobs;
      try {
        jobs = await _list(
          '/print-jobs/',
          query: {
            'restaurant': _restaurantId,
            'status': status,
            'page_size': 100,
            'ordering': 'created_at',
          },
        );
      } on ApiException catch (error) {
        if (!error.isConnectivity) rethrow;
        return;
      }
      AppLogger.instance.info(
        'print_jobs_poll',
        data: {
          'status': status,
          'found': jobs.length,
          'restaurant': _restaurantId,
        },
      );
      for (final job in jobs) {
        if ('${job['status']}' == 'scheduled') {
          final availableAt = DateTime.tryParse(
            '${job['available_at'] ?? ''}',
          )?.toLocal();
          if (availableAt != null && availableAt.isAfter(DateTime.now())) {
            if (nextScheduledAt == null ||
                availableAt.isBefore(nextScheduledAt)) {
              nextScheduledAt = availableAt;
            }
          }
          continue;
        }
        final jobId = '${job['id']}';
        final printer = availablePrinters['${job['printer']}'];
        if (printer == null) {
          AppLogger.instance.warning(
            'print_job_skipped_printer_unavailable',
            data: {'job_id': jobId, 'printer_id': job['printer']},
          );
          continue;
        }
        final payload = job['payload'] as Map<String, dynamic>? ?? const {};
        if (payload['manual_only'] == true) {
          // Sem este registro, um trabalho marcado como manual sumia sem
          // deixar rastro: "não imprimiu e não deu erro" ficava impossível de
          // diagnosticar sem acesso ao banco.
          AppLogger.instance.info(
            'print_job_skipped_manual_only',
            data: {'job_id': jobId, 'printer_id': job['printer']},
          );
          continue;
        }
        final document = PrintDocument.fromRemoteJob(job);
        final isAutomaticWeighTicket =
            document.type == PrintJobType.weighTicket;
        if (printer['auto_print'] != true && !isAutomaticWeighTicket) {
          AppLogger.instance.info(
            'print_job_skipped_auto_print_off',
            data: {'job_id': jobId, 'printer_id': printer['id']},
          );
          continue;
        }
        if (document.isEmpty) {
          AppLogger.instance.warning(
            'print_job_sem_conteudo',
            data: {'job_id': jobId},
          );
          continue;
        }
        if (queue == null || scope == null) {
          // Caminho degradado: o banco local não abriu (disco cheio, arquivo
          // corrompido). O PDV já avisou disso na inicialização; um
          // restaurante com internet funcionando não pode ficar sem imprimir
          // também por causa disso.
          await _printWithoutQueue(
            jobId: jobId,
            printer: printer,
            document: document,
          );
          ingested++;
          continue;
        }
        // `remoteJobId` é a chave que impede o mesmo cupom de entrar duas
        // vezes: enquanto o `mark-printed` não é confirmado, o trabalho volta
        // a aparecer nesta consulta.
        await queue.enqueue(
          scope: scope,
          jobId: jobId,
          remoteJobId: jobId,
          printer: printer,
          jobType: document.wireType,
          content: document.content,
          barcode: document.barcode,
          qr: document.qr,
        );
        ingested++;
      }
    }

    if (nextScheduledAt != null && _token != null) {
      final wait = nextScheduledAt.difference(DateTime.now());
      AppLogger.instance.info(
        'print_jobs_next_scheduled',
        data: {
          'available_at': nextScheduledAt.toIso8601String(),
          'wait_ms': wait.inMilliseconds,
        },
      );
      _scheduledPrintTimer = Timer(
        wait.isNegative
            ? const Duration(milliseconds: 100)
            : wait + const Duration(milliseconds: 150),
        () => unawaited(_guarded(_processPrintJobs)),
      );
    } else if (ingested == 0) {
      AppLogger.instance.info(
        'print_jobs_poll_idle',
        data: {'restaurant': _restaurantId},
      );
    }
  }

  /// Trabalhos já impressos cujo `mark-printed` ainda não foi aceito.
  ///
  /// Só do caminho degradado (sem banco local). Com a fila, quem lembra disso
  /// é o estado `PRINTED` no disco — que sobrevive a fechar o PDV, enquanto
  /// este conjunto se perde.
  final Set<String> _confirmingJobIds = {};

  /// Imprime um trabalho do servidor sem passar pela fila local.
  ///
  /// Existe só para o caso em que o banco local não abriu. Sem retentativa
  /// durável: se a impressora recusar, o servidor é avisado e o trabalho volta
  /// a aparecer no próximo ciclo — o comportamento que existia antes da fila.
  Future<void> _printWithoutQueue({
    required String jobId,
    required Map<String, dynamic> printer,
    required PrintDocument document,
  }) async {
    if (_confirmingJobIds.contains(jobId)) {
      // O papel já saiu num ciclo anterior; só a confirmação não passou.
      // Reimprimir aqui seria o mesmo cupom saindo pela segunda vez.
      try {
        await api.post(
          '/print-jobs/$jobId/mark-printed/',
          body: const {},
          accessToken: _token,
        );
        _confirmingJobIds.remove(jobId);
      } catch (_) {
        // Continua pendente; o próximo ciclo tenta de novo.
      }
      return;
    }
    var printed = false;
    try {
      await Printer.forDocument(
        printer,
        document,
        runtime: printing,
      ).send(document);
      printed = true;
      await api.post(
        '/print-jobs/$jobId/mark-printed/',
        body: const {},
        accessToken: _token,
      );
      AppLogger.instance.info(
        'print_job_printed',
        data: {'job_id': jobId, 'printer_id': printer['id'], 'fila': false},
      );
    } catch (error) {
      if (printed) {
        _confirmingJobIds.add(jobId);
        AppLogger.instance.warning(
          'print_job_printed_but_not_confirmed',
          data: {'job_id': jobId, 'message': '$error'},
        );
        return;
      }
      AppLogger.instance.error(
        'print_job_failed',
        cause: error,
        data: {'job_id': jobId, 'printer_id': printer['id']},
      );
      try {
        await api.post(
          '/print-jobs/$jobId/mark-failed/',
          body: {'error': 'Falha no PDV Desktop: $error'},
          accessToken: _token,
        );
      } catch (_) {
        // Sem servidor não há o que avisar agora.
      }
    }
  }

  /// Coloca na fila local um cupom montado por este terminal e tenta
  /// imprimi-lo agora.
  ///
  /// É o caminho de toda impressão nascida no PDV: quem chama escolhe a
  /// impressora ([KitchenPrinter], [ReceiptPrinter], ...) e entrega o
  /// documento; a fila cuida da segunda chance.
  ///
  /// Devolve duas coisas diferentes de propósito:
  ///
  /// - `accepted`: este terminal assumiu a impressão. É o que decide se o
  ///   backend deve ficar de fora (`offline_printed`). Uma impressora sem
  ///   papel **não** muda isso: o trabalho está na fila e sai quando ela
  ///   voltar. Usar "saiu o papel" aqui faria o backend imprimir uma segunda
  ///   via quando a fila sincronizasse, e a fila local imprimiria a primeira
  ///   depois — duas comandas para a mesma rodada.
  /// - `printed`: o papel saiu agora. Interessa a quem está olhando a
  ///   impressora esperando o cupom, para mostrar o erro na hora.
  ///
  /// Sem armazenamento local vinculado (uma janela ainda sem sessão), imprime
  /// direto: melhor sair sem rede de segurança do que não sair. Aí as duas
  /// respostas coincidem, porque não há fila para garantir a segunda chance.
  Future<({bool accepted, bool printed})> submit(
    Printer printer,
    PrintDocument document,
  ) async {
    final queue = _printQueue;
    final scope = _printScope;
    if (queue == null || scope == null || !printer.queueable) {
      await printer.send(document);
      return (accepted: true, printed: true);
    }
    final jobId = await queue.enqueue(
      scope: scope,
      printer: printer.device.raw,
      jobType: document.wireType,
      content: document.content,
      barcode: document.barcode,
      qr: document.qr,
    );
    AppLogger.instance.info(
      'print_job_enfileirado',
      data: {
        'job_id': jobId,
        'job_type': document.wireType,
        'printer': printer.device.label,
        'setor': printer.device.sector,
      },
    );
    await drainPrintQueue();
    var status = await queue.statusOf(jobId);
    if (status == PrintJobStatus.pending) {
      // Uma drenagem já estava em andamento quando este cupom entrou, e pode
      // ter passado pela fila antes dele. Sem este segundo giro, quem está
      // olhando a impressora ouviria "está na fila" com a impressora livre.
      await drainPrintQueue();
      status = await queue.statusOf(jobId);
    }
    AppLogger.instance.info(
      'print_job_resultado',
      data: {
        'job_id': jobId,
        'printer': printer.device.label,
        'estado': status?.name ?? 'desconhecido',
      },
    );
    return (
      // Recusa definitiva (impressora sem endereço) devolve a impressão ao
      // backend: nenhuma repetição aqui resolveria.
      accepted: status != PrintJobStatus.failed,
      printed: status == PrintJobStatus.printed,
    );
  }

  /// Imprime o que está na fila local, um trabalho de cada vez.
  ///
  /// Não depende de rede em nenhum ponto. Uma falha de comunicação com a
  /// impressora — papel, cabo, equipamento desligado — devolve o trabalho para
  /// a fila com espera crescente; antes ele simplesmente se perdia, e a
  /// cozinha ficava sem a comanda sem ninguém saber.
  Future<void> drainPrintQueue({int limit = 20}) {
    // Uma drenagem por vez neste processo: o timer da fila, o evento do WS e
    // um cupom recém-montado chegam aqui ao mesmo tempo o tempo todo.
    final running = _drainInFlight;
    if (running != null) return running;
    final drain = _drainPrintQueue(limit: limit);
    _drainInFlight = drain;
    return drain.whenComplete(() {
      if (identical(_drainInFlight, drain)) _drainInFlight = null;
    });
  }

  Future<void> _drainPrintQueue({required int limit}) async {
    final queue = _printQueue;
    final scope = _printScope;
    if (queue == null || scope == null) return;
    final before = await queue.summary(scope: scope);
    if (before.pending == 0 && before.failed == 0) return;

    // Impressoras que já falharam nesta rodada. Antes, a primeira falha
    // encerrava a drenagem inteira — "a impressora é a mesma", o que só vale
    // quando existe uma. Com um cupom do bar travado numa térmica de rede
    // fora do ar, a comanda da cozinha ficava esperando atrás dele em toda
    // rodada, sem erro nenhum na tela: "não imprimiu e não avisou".
    final unreachable = <String>{};
    var printed = 0;
    var retried = 0;
    var failed = 0;
    var skipped = 0;
    var exhausted = 0;

    for (var processed = 0; processed < limit; processed++) {
      final job = await queue.claimNext(scope: scope);
      if (job == null) break;
      final document = PrintDocument.fromQueueEntry(job);
      final printer = Printer.forDocument(
        job.printer,
        document,
        runtime: printing,
      );
      final resource = printer.device.lockResource;
      if (unreachable.contains(resource)) {
        // Já sabemos que este equipamento não responde agora: insistir custa
        // um tempo limite inteiro e atrasa as outras impressoras da fila.
        skipped++;
        await queue.markRetry(
          job.id,
          attempts: job.attempts + 1,
          error: 'Equipamento sem resposta nesta rodada.',
        );
        continue;
      }
      try {
        await printer.send(document);
        await queue.markPrinted(job.id);
        printed++;
        AppLogger.instance.info(
          'print_job_printed',
          data: {
            'job_id': job.jobId,
            'job_type': job.jobType,
            'printer_id': job.printerId,
            'printer': printer.device.label,
          },
        );
      } on PrinterCommunicationException catch (error) {
        final attempts = job.attempts + 1;
        final outcome = await queue.markRetry(
          job.id,
          attempts: attempts,
          error: error.message,
        );
        // A próxima tentativa DESTE equipamento só faz sentido depois da
        // espera; os cupons das outras impressoras seguem na mesma rodada.
        unreachable.add(resource);
        if (outcome.exhausted) {
          exhausted++;
          AppLogger.instance.error(
            'print_job_esgotado',
            data: {
              'job_id': job.jobId,
              'job_type': job.jobType,
              'printer': printer.device.label,
              'tentativas': attempts,
              'motivo': error.message,
            },
          );
          // O servidor precisa saber que este cupom não vai sair sozinho:
          // sem isso o trabalho fica "pendente" lá para sempre.
          await _reportRemoteFailure(job, error);
        } else {
          retried++;
          AppLogger.instance.warning(
            'print_job_retry',
            data: {
              'job_id': job.jobId,
              'job_type': job.jobType,
              'printer': printer.device.label,
              'tentativa': '$attempts/${PrintQueueService.maximumAttempts}',
              'proxima_em_s': outcome.nextRetryAt!
                  .difference(DateTime.now().toUtc())
                  .inSeconds,
              'motivo': error.message,
            },
          );
        }
      } catch (error) {
        // Erro que nenhuma repetição resolve (conteúdo inválido, configuração
        // impossível): sai da rotação e fica visível para revisão.
        await queue.markFailed(job.id, error: '$error');
        failed++;
        AppLogger.instance.error(
          'print_job_failed',
          cause: error,
          data: {
            'job_id': job.jobId,
            'job_type': job.jobType,
            'printer': printer.device.label,
          },
        );
        await _reportRemoteFailure(job, error);
      }
    }
    await queue.purgeConfirmed(scope: scope);
    final after = await queue.summary(scope: scope);
    AppLogger.instance.info(
      'print_queue_drain',
      data: {
        'na_fila_antes': before.pending,
        'impressos': printed,
        'reagendados': retried,
        'adiados': skipped,
        'sem_tentativas': exhausted,
        'recusados': failed,
        'ainda_na_fila': after.pending,
        'com_falha': after.failed,
      },
    );
  }

  /// Avisa o servidor sobre os trabalhos que já saíram no papel.
  ///
  /// O papel ter saído e o servidor ter sido avisado são coisas diferentes.
  /// Sem rede a confirmação espera, e o trabalho **não** volta a imprimir —
  /// quem garante isso é o estado `PRINTED` na fila local, que antes só
  /// existia na memória do processo e se perdia ao fechar o PDV.
  Future<void> _confirmPrintedJobs() async {
    final queue = _printQueue;
    final scope = _printScope;
    if (queue == null || scope == null) return;
    for (final job in await queue.awaitingConfirmation(scope: scope)) {
      try {
        await api.post(
          '/print-jobs/${job.remoteJobId}/mark-printed/',
          body: const {},
          accessToken: _token,
        );
        await queue.forget(job.id);
      } on ApiException catch (error) {
        if (!error.isConnectivity) {
          // O servidor recusou (o trabalho já foi cancelado lá, por exemplo).
          // Insistir não muda nada, e a nota já está com o cliente.
          await queue.forget(job.id);
          continue;
        }
        AppLogger.instance.info(
          'print_job_confirmacao_adiada',
          data: {'job_id': job.remoteJobId},
        );
        return;
      }
    }
  }

  Future<void> _reportRemoteFailure(PrintQueueEntry job, Object error) async {
    final remoteId = job.remoteJobId;
    if (remoteId == null) return;
    try {
      await api.post(
        '/print-jobs/$remoteId/mark-failed/',
        body: {'error': 'Falha no PDV Desktop: $error'},
        accessToken: _token,
      );
    } on ApiException {
      // Sem servidor não há o que avisar agora. O trabalho continua marcado
      // como recusado aqui, que é o que a tela de revisão mostra.
    }
  }

  /// Imprime agora um `PrintJob` renderizado pelo servidor, a pedido do
  /// operador — sem fila, porque quem clicou está olhando a impressora.
  Future<void> printJobManually(
    Map<String, dynamic> job,
    Map<String, dynamic> printer,
  ) async {
    // O papel vale mais que o registro: num Caixa Secundário este agente fica
    // parado de propósito (quem serve a fila da nuvem é o Principal), e exigir
    // sessão aqui fazia o botão "imprimir" não produzir nada num terminal com
    // impressora própria e cupom já renderizado na mão.
    final token = _token;
    final jobId = '${job['print_job_id'] ?? job['id'] ?? ''}'.trim();
    final document = PrintDocument.fromRemoteJob(job);
    if (document.isEmpty) {
      throw StateError('O trabalho não possui conteúdo para impressão.');
    }
    // O papel já ter saído e o servidor não ter sido avisado são coisas
    // diferentes: tratar as duas como "falha na impressão" mostrava erro numa
    // nota que o operador tinha na mão e ainda marcava o trabalho como
    // falho — deixando-o elegível para sair de novo.
    var printed = false;
    try {
      await Printer.forDocument(
        printer,
        document,
        runtime: printing,
      ).send(document);
      printed = true;
      // Sem sessão ou sem id remoto não há o que confirmar: o cupom já está
      // com o operador, e é isso que ele pediu.
      if (token == null || jobId.isEmpty) return;
      await api.post(
        '/print-jobs/$jobId/mark-printed/',
        body: const {},
        accessToken: token,
      );
    } catch (error) {
      if (printed) {
        AppLogger.instance.warning(
          'print_job_printed_but_not_confirmed',
          data: {'job_id': jobId, 'message': '$error'},
        );
        return;
      }
      if (token != null && jobId.isNotEmpty) {
        await api.post(
          '/print-jobs/$jobId/mark-failed/',
          body: {'error': 'Falha na impressão manual: $error'},
          accessToken: token,
        );
      }
      rethrow;
    }
  }

  /// Revalida os equipamentos sem bloquear a tela de vendas.
  Future<PrinterAvailability> refreshPrinterAvailability({
    bool useCachedDevices = false,
  }) async {
    if (_token == null || _restaurantId == null) {
      const status = PrinterAvailability.notConfigured;
      printerAvailability.value = status;
      return status;
    }
    printerAvailability.value = PrinterAvailability.checking;
    try {
      if (!useCachedDevices || _printers.isEmpty) {
        await _syncDevicesIfNeeded();
      }
      final candidates = _printers
          .map(PrinterDevice.fromJson)
          .where((device) => device.isAddressable)
          .toList();
      if (candidates.isEmpty) {
        const status = PrinterAvailability.notConfigured;
        printerAvailability.value = status;
        return status;
      }
      for (final device in candidates) {
        if (await GenericPrinter(device, runtime: printing).probe()) {
          const status = PrinterAvailability.available;
          printerAvailability.value = status;
          return status;
        }
      }
    } catch (_) {
      // A indisponibilidade vira estado visual; nunca encerra a tela de venda.
    }
    const status = PrinterAvailability.disconnected;
    printerAvailability.value = status;
    return status;
  }

  Future<bool> checkPrinterAvailability(
    Map<String, dynamic> printer, {
    bool publish = true,
  }) async {
    final device = PrinterDevice.fromJson(printer);
    final available =
        device.isAddressable &&
        await GenericPrinter(device, runtime: printing).probe();
    if (publish) {
      printerAvailability.value = available
          ? PrinterAvailability.available
          : PrinterAvailability.disconnected;
    }
    return available;
  }

  /// Impressoras que este terminal já conhece.
  ///
  /// Vive em memória depois da primeira sincronização, então continua
  /// disponível com a rede fora — que é exatamente quando a comanda precisa
  /// ser montada e impressa aqui, sem esperar o backend renderizar o job.
  /// Depender de uma releitura de `/printers/` nessa hora não funciona: o
  /// cache de resposta só responde se aquela consulta exata já tiver sido
  /// feita on-line antes.
  List<Map<String, dynamic>> get knownPrinters => List.unmodifiable(_printers);

  /// Devolve as impressoras conhecidas, sincronizando se ainda não houver
  /// nenhuma. Nunca lança: sem rede e sem cache, devolve o que existir.
  Future<List<Map<String, dynamic>>> ensurePrinters() async {
    if (_printers.isEmpty) {
      try {
        await _syncDevicesIfNeeded();
      } catch (_) {
        // Segue com a lista em memória, mesmo vazia — quem chama decide o
        // que dizer ao operador.
      }
    }
    if (_printers.isEmpty) {
      // Sem impressora conhecida, o roteamento por setor não tem o que
      // escolher e a comanda simplesmente não existe — sem erro em lugar
      // nenhum. Quase sempre é o agente parado (terminal secundário, ou
      // restaurante ainda não definido), e não cadastro faltando.
      AppLogger.instance.warning(
        'print_agent_sem_impressoras',
        data: {
          'agente_ativo': isRunning,
          'restaurante': _restaurantId,
        },
      );
    }
    return knownPrinters;
  }

  Future<void> _syncDevicesIfNeeded() async {
    final now = DateTime.now();
    if (_lastDeviceSync != null &&
        now.difference(_lastDeviceSync!) < const Duration(seconds: 30)) {
      return;
    }
    final existing = _deviceSyncInFlight;
    if (existing != null) return existing;

    final sync =
        _list(
          '/printers/',
          query: {
            'restaurant': _restaurantId,
            'is_active': true,
            'page_size': 100,
          },
        ).then(
          // Sem override local: a impressora vale como está cadastrada.
          (printers) => _printers = printers,
        );
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
}
