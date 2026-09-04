import 'dart:async';

import '../../logging/app_logger.dart';
import 'package:flutter_libserialport/flutter_libserialport.dart';
import '../peripheral_lock.dart';
import 'scale_protocol.dart';
import 'scale_sample.dart';
import 'scale_transport.dart';

/// Lê o peso direto do equipamento, sem intermediários.
///
/// O fluxo é totalmente local: a porta serial é aberta por este processo, os
/// quadros são decodificados pelo protocolo do fabricante e a estabilidade é
/// resolvida aqui. Nenhuma chamada à API participa da leitura — a estação
/// pesa e conclui mesmo com o servidor fora do ar.
///
/// A porta é reservada por [PeripheralLock] antes da abertura, de modo que
/// duas janelas nunca disputem o mesmo equipamento e a segunda saiba quem
/// detém a posse.
class SerialScaleReader {
  SerialScaleReader({
    required this.portName,
    required this.protocol,
    required this.transportFactory,
    this.stabilityToleranceKg = 0.002,
    this.settleDuration = const Duration(seconds: 2),
    this.zeroThresholdKg = 0.005,
    this.silenceTimeout = const Duration(seconds: 4),
    this.role = 'balanca-rapida',
    this.ownerDetail,
  });

  /// Constrói um leitor ligado a uma porta serial real.
  factory SerialScaleReader.serial({
    required String portName,
    required int baudRate,
    required ScaleProtocol protocol,
    double stabilityToleranceKg = 0.002,
    Duration settleDuration = const Duration(seconds: 2),
    double zeroThresholdKg = 0.005,
    Duration silenceTimeout = const Duration(seconds: 4),
    String role = 'balanca-rapida',
    String? ownerDetail,
  }) {
    // Extrai configuração serial do protocolo, se houver.
    final cfg = protocol.serialConfig;
    dynamic parity;
    int? stopBits;
    if (cfg != null) {
      if (cfg.containsKey('parity')) {
        final p = cfg['parity'];
        if (p == 1) {
          parity = SerialPortParity.odd;
        } else if (p == 2) {
          parity = SerialPortParity.even;
        } else {
          parity = SerialPortParity.none;
        }
      }
      if (cfg.containsKey('stopBits')) stopBits = cfg['stopBits'];
    }

    return SerialScaleReader(
      portName: portName,
      protocol: protocol,
      stabilityToleranceKg: stabilityToleranceKg,
      settleDuration: settleDuration,
      zeroThresholdKg: zeroThresholdKg,
      silenceTimeout: silenceTimeout,
      role: role,
      ownerDetail: ownerDetail,
      transportFactory: () => SerialScaleTransport(
        portName: portName,
        baudRate: baudRate,
        parity: parity,
        stopBits: stopBits,
      ),
    );
  }

  static const _maximumRetryDelay = Duration(seconds: 15);

  final String portName;
  final ScaleProtocol protocol;
  final double stabilityToleranceKg;
  final Duration settleDuration;
  final double zeroThresholdKg;
  final Duration silenceTimeout;
  final String role;
  final String? ownerDetail;

  /// Abre o canal com o equipamento. Injetável para permitir testes sem
  /// hardware conectado.
  final ScaleTransport Function() transportFactory;

  final _samples = StreamController<ScaleSample>.broadcast();
  final _statuses = StreamController<ScaleLinkStatus>.broadcast();

  ScaleTransport? _transport;
  StreamSubscription<List<int>>? _subscription;
  PeripheralLock? _lock;
  Timer? _watchdog;
  Timer? _retryTimer;
  int _retryAttempt = 0;
  bool _started = false;
  bool _disposed = false;

  DateTime? _openedAt;
  DateTime? _lastByteAt;
  DateTime? _lastSampleAt;
  DateTime? _lastWeightAt;
  String? _undecodedSample;
  DateTime? _stableSince;
  DateTime? _lastWeightRequestAt;
  double _referenceWeight = 0;
  ScaleSample? _lastSample;

  ScaleLinkStatus _status = const ScaleLinkStatus(
    state: ScaleLinkState.disconnected,
    message: 'Balança não conectada.',
  );

  Stream<ScaleSample> get samples => _samples.stream;
  Stream<ScaleLinkStatus> get statusChanges => _statuses.stream;
  ScaleLinkStatus get status => _status;
  ScaleSample? get lastSample => _lastSample;

  /// Peso atual considerado zerado (prato vazio).
  bool get isAtZero => (_lastSample?.weightKg ?? 0) <= zeroThresholdKg;

  Future<void> start() async {
    if (_disposed || _started) return;
    _started = true;
    await _connect();
  }

  Future<void> _connect() async {
    if (_disposed || !_started) return;
    _publish(
      ScaleLinkStatus(
        state: ScaleLinkState.connecting,
        message: 'Abrindo $portName...',
        portName: portName,
      ),
    );

    final resource = 'scale:$portName';
    final lock = await PeripheralLock.tryAcquire(
      resource,
      role: role,
      detail: ownerDetail,
    );
    if (lock == null) {
      final owner = await PeripheralLock.currentOwner(resource);
      _publish(
        ScaleLinkStatus(
          state: ScaleLinkState.portBusy,
          message: owner == null
              ? '$portName já está reservada por outra janela do StarChef.'
              : '$portName está reservada por ${owner.describe()}.',
          portName: portName,
          owner: owner?.describe(),
        ),
      );
      _scheduleRetry();
      return;
    }
    _lock = lock;

    try {
      final transport = transportFactory();
      final stream = await transport.open();
      if (_disposed || !_started) {
        await transport.close();
        await _releaseLock();
        return;
      }
      _transport = transport;
      protocol.reset();
      _subscription = stream.listen(
        _onBytes,
        onError: (Object error) => unawaited(_handleFailure('$error')),
        onDone: () => unawaited(_handleFailure('A porta $portName fechou.')),
        cancelOnError: false,
      );
      _retryAttempt = 0;
      _openedAt = DateTime.now();
      _lastByteAt = null;
      _lastSampleAt = null;
      _lastWeightAt = null;
      _undecodedSample = null;
      _publish(
        ScaleLinkStatus(
          state: ScaleLinkState.connecting,
          message: 'Conectado a $portName, aguardando leitura.',
          portName: portName,
        ),
      );
      _watchdog?.cancel();
      _watchdog = Timer.periodic(
        const Duration(seconds: 1),
        (_) => _checkSilence(),
      );
      AppLogger.instance.info(
        'scale_port_open',
        data: {'port': portName, 'protocol': protocol.id},
      );
    } on ScaleTransportException catch (error) {
      await _releaseLock();
      _publish(
        ScaleLinkStatus(
          state: error.portBusy
              ? ScaleLinkState.portBusy
              : ScaleLinkState.readError,
          message: error.message,
          portName: portName,
        ),
      );
      _scheduleRetry();
    } catch (error) {
      await _releaseLock();
      _publish(
        ScaleLinkStatus(
          state: ScaleLinkState.readError,
          message: 'Falha inesperada ao abrir $portName: $error',
          portName: portName,
        ),
      );
      _scheduleRetry();
    }
  }

  void _onBytes(List<int> bytes) {
    if (_disposed) return;
    if (bytes.isEmpty) return;
    _lastByteAt = DateTime.now();
    final decoded = protocol.decode(bytes);
    if (decoded.isEmpty) {
      // Guardado para o aviso de protocolo errado: sem ver o que chegou, quem
      // atende a loja não tem como saber se o cadastro aponta o fabricante
      // certo. É uma amostra curta, só o suficiente para reconhecer o
      // enquadramento.
      if (_undecodedSample == null) {
        _undecodedSample = _describeBytes(bytes);
        AppLogger.instance.warning(
          'scale_frame_not_decoded',
          data: {
            'port': portName,
            'protocol': protocol.id,
            'bruto': _undecodedSample,
          },
        );
      }
      return;
    }
    _undecodedSample = null;
    _lastSampleAt = _lastByteAt;
    // Um quadro só de estado (`hasWeight == false`) prova que o protocolo
    // está certo, mas não é leitura de peso: sem separar os dois, uma balança
    // que só anuncia estabilidade aparecia como "lendo normalmente" e o
    // operador ficava olhando um peso que nunca chegava.
    if (decoded.any((sample) => sample.hasWeight)) _lastWeightAt = _lastByteAt;
    for (final sample in decoded) {
      _emit(sample);
    }
  }

  /// Amostra legível dos bytes crus, para o aviso na tela e para o log.
  static String _describeBytes(List<int> bytes) {
    final visible = bytes.take(24).map((byte) {
      if (byte >= 32 && byte <= 126) return String.fromCharCode(byte);
      return '<${byte.toRadixString(16).padLeft(2, '0').toUpperCase()}>';
    }).join();
    return bytes.length > 24 ? '$visible...' : visible;
  }

  void _emit(ScaleSample sample) {
    final now = sample.at;
    final drifted =
        (sample.weightKg - _referenceWeight).abs() > stabilityToleranceKg;
    if (drifted) {
      _referenceWeight = sample.weightKg;
      _stableSince = now;
    } else if (sample.stable == false) {
      // O equipamento avisou que ainda está em movimento; a contagem recomeça
      // mesmo que o valor numérico esteja repetido.
      _stableSince = now;
    } else {
      _stableSince ??= now;
    }

    final settled =
        _stableSince != null &&
        now.difference(_stableSince!) >= settleDuration &&
        sample.stable != false;

    final resolved = ScaleSample(
      weightKg: sample.weightKg,
      raw: sample.raw,
      stable: settled,
      negative: sample.negative,
      at: now,
    );
    _lastSample = resolved;
    _publish(
      ScaleLinkStatus(
        state: ScaleLinkState.connected,
        message: settled
            ? 'Peso estável: ${resolved.weightKg.toStringAsFixed(3)} kg.'
            : 'Recebendo peso: ${resolved.weightKg.toStringAsFixed(3)} kg.',
        portName: portName,
        lastSampleAt: now,
      ),
    );
    if (!_samples.isClosed) _samples.add(resolved);

    // Se o equipamento enviou apenas um indicador de estabilidade (sem
    // valor numérico), solicitamos o peso explicitamente. Limitamos a
    // frequência das solicitações para evitar flood (1s).
    if (!resolved.hasWeight && resolved.stable == true) {
      final nowTime = DateTime.now();
      if (_lastWeightRequestAt == null ||
          nowTime.difference(_lastWeightRequestAt!) >
              const Duration(seconds: 1)) {
        _lastWeightRequestAt = nowTime;
        try {
          unawaited(requestWeight());
        } catch (_) {
          // Não deixamos uma exceção impedir o fluxo normal.
        }
      }
    }
  }

  /// Diz por que o peso não está chegando, em vez de esperar calado.
  ///
  /// Antes esta checagem desistia quando nada tinha chegado desde a abertura —
  /// justamente o caso mais comum e mais difícil de diagnosticar. A estação
  /// ficava em "Conectado a COM3, aguardando leitura" para sempre, com a
  /// mesma frase para uma porta trocada, um cabo solto, um protocolo errado
  /// no cadastro e uma balança em modo sob demanda. Cada um desses tem uma
  /// providência diferente, então cada um ganha a sua frase.
  void _checkSilence() {
    if (_disposed) return;
    final openedAt = _openedAt;
    if (openedAt == null) return;

    final now = DateTime.now();
    final lastByte = _lastByteAt;

    // 1. Porta aberta, nenhum byte: ninguém do outro lado.
    if (lastByte == null) {
      if (now.difference(openedAt) > silenceTimeout) {
        _publish(
          ScaleLinkStatus(
            state: ScaleLinkState.noResponse,
            message:
                'A porta $portName abriu, mas nada chegou dela. Confira se é '
                'mesmo a porta da balança, o cabo e o baud rate cadastrado. '
                'Se o visor mostra o peso, o equipamento pode estar em modo '
                'sob demanda: use "Pegar peso da balança".',
            portName: portName,
          ),
        );
      }
      return;
    }

    // 2. Bytes chegando e nenhum peso saindo deles. São duas causas
    //    diferentes, e a providência de cada uma também é.
    final lastWeight = _lastWeightAt;
    if (lastWeight == null && now.difference(lastByte) < silenceTimeout) {
      final raw = _undecodedSample;
      _publish(
        ScaleLinkStatus(
          state: ScaleLinkState.readError,
          message: _lastSampleAt == null
              ? 'A balança está transmitindo em $portName, mas nada do que ela '
                    'envia é legível como ${protocol.label}. Confira o '
                    'protocolo no cadastro do equipamento'
                    '${raw == null ? '' : '. Recebido: $raw'}'
              : 'A balança está respondendo em $portName, mas só com estado — '
                    'nenhum peso. Confira o modo de transmissão contínua do '
                    'equipamento e o protocolo no cadastro.',
          portName: portName,
        ),
      );
      return;
    }

    // 3. Já leu peso e parou.
    if (now.difference(lastByte) > silenceTimeout &&
        _status.state == ScaleLinkState.connected) {
      _publish(
        ScaleLinkStatus(
          state: ScaleLinkState.noResponse,
          message:
              'A balança parou de transmitir em $portName. Verifique o cabo '
              'e o modo de transmissão contínua do equipamento.',
          portName: portName,
          lastSampleAt: lastWeight,
        ),
      );
    }
  }

  Future<void> _handleFailure(String message) async {
    if (_disposed || !_started) return;
    AppLogger.instance.warning(
      'scale_port_failure',
      data: {'port': portName, 'message': message},
    );
    await _teardownTransport();
    _publish(
      ScaleLinkStatus(
        state: ScaleLinkState.readError,
        message: message,
        portName: portName,
      ),
    );
    _scheduleRetry();
  }

  void _scheduleRetry() {
    if (_disposed || !_started) return;
    _retryTimer?.cancel();
    _retryAttempt = (_retryAttempt + 1).clamp(1, 5);
    final seconds = (1 << (_retryAttempt - 1)).clamp(
      1,
      _maximumRetryDelay.inSeconds,
    );
    _retryTimer = Timer(
      Duration(seconds: seconds),
      () => unawaited(_connect()),
    );
  }

  void _publish(ScaleLinkStatus next) {
    if (_disposed || next == _status) return;
    _status = next;
    if (!_statuses.isClosed) _statuses.add(next);
  }

  /// Pede uma pesagem ao equipamento — o "pegar peso" de emergência.
  ///
  /// Serve a dois cenários em que a estação não recebe nada: a balança está
  /// configurada para responder só sob comando, ou o canal caiu e precisa ser
  /// reaberto. Reconectar antes de pedir cobre os dois de uma vez.
  ///
  /// Não força nem inventa leitura: se o equipamento não responder, o estado
  /// continua o mesmo e o operador tem a entrada manual como saída.
  Future<ScaleWeightRequest> requestWeight() async {
    if (_disposed) return ScaleWeightRequest.unavailable;
    if (!_started) return ScaleWeightRequest.unavailable;

    if (_transport == null || _status.state != ScaleLinkState.connected) {
      // Canal fechado, em erro ou sem resposta: reabrir é o primeiro socorro.
      _retryTimer?.cancel();
      _retryAttempt = 0;
      await _teardownTransport();
      await _connect();
    }
    final transport = _transport;
    if (transport == null) return ScaleWeightRequest.notConnected;

    // A contagem recomeça para que a resposta seja avaliada do zero, e não
    // aproveite a estabilidade de uma leitura antiga.
    resetStability();
    final sent = await transport.write(protocol.weightRequest);
    AppLogger.instance.info(
      'scale_weight_requested',
      data: {'port': portName, 'protocol': protocol.id, 'sent': sent},
    );
    return sent
        ? ScaleWeightRequest.sent
        : ScaleWeightRequest.writeNotSupported;
  }

  /// Zera a contagem de estabilidade — usado após concluir um pedido.
  void resetStability() {
    _stableSince = null;
    _referenceWeight = 0;
    _lastSample = null;
  }

  Future<void> _teardownTransport() async {
    _watchdog?.cancel();
    _watchdog = null;
    _openedAt = null;
    await _subscription?.cancel();
    _subscription = null;
    final transport = _transport;
    _transport = null;
    if (transport != null) {
      try {
        await transport.close();
      } catch (_) {
        // A porta pode já ter sido removida do sistema.
      }
    }
    await _releaseLock();
  }

  Future<void> _releaseLock() async {
    final lock = _lock;
    _lock = null;
    await lock?.release();
  }

  Future<void> stop() async {
    _started = false;
    _retryTimer?.cancel();
    _retryTimer = null;
    await _teardownTransport();
    _publish(
      const ScaleLinkStatus(
        state: ScaleLinkState.disconnected,
        message: 'Balança desconectada.',
      ),
    );
  }

  Future<void> dispose() async {
    if (_disposed) return;
    await stop();
    _disposed = true;
    await _samples.close();
    await _statuses.close();
  }
}
