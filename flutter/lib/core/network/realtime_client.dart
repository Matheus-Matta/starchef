import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// Um evento recebido do `/ws/realtime/`: `{"event": ..., "payload": ...}`.
class RealtimeEvent {
  const RealtimeEvent(this.event, this.payload);

  final String event;
  final Map<String, dynamic> payload;
}

/// Conexão de push do backend, com reconexão automática.
///
/// Existe para que quem precisa saber "algo mudou no servidor" assine
/// [events] em vez de perguntar à API em um intervalo fixo. A única consulta
/// de segurança é [onConnected]: dispara ao conectar e a cada reconexão, para
/// cobrir o que pode ter sido perdido enquanto a conexão estava caída — nunca
/// um timer recorrente.
class RealtimeClient {
  RealtimeClient({required this.urlBuilder, this.headersBuilder});

  /// Reconstrói a URL a cada tentativa: o token pode ter sido renovado entre
  /// uma queda de conexão e a próxima tentativa.
  final String Function() urlBuilder;

  /// Headers reconstruídos em cada reconexão. O PDV envia o JWT como Bearer
  /// para que a credencial não apareça na URL ou em logs de proxy.
  final Map<String, dynamic> Function()? headersBuilder;

  static const _backoffSeconds = [2, 3, 5, 10, 20, 30];

  final _eventsController = StreamController<RealtimeEvent>.broadcast();
  final _connectedController = StreamController<void>.broadcast();

  WebSocket? _socket;
  StreamSubscription? _subscription;
  Timer? _reconnectTimer;
  Timer? _heartbeatTimer;
  DateTime? _lastMessageAt;
  int _attempt = 0;
  bool _stopped = true;

  Stream<RealtimeEvent> get events => _eventsController.stream;
  Stream<void> get onConnected => _connectedController.stream;

  void start() {
    if (!_stopped) return;
    _stopped = false;
    _attempt = 0;
    unawaited(_connect());
  }

  void stop() {
    _stopped = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    unawaited(_subscription?.cancel());
    _subscription = null;
    unawaited(_socket?.close());
    _socket = null;
  }

  void dispose() {
    stop();
    unawaited(_eventsController.close());
    unawaited(_connectedController.close());
  }

  Future<void> _connect() async {
    if (_stopped) return;
    try {
      final socket = await WebSocket.connect(
        urlBuilder(),
        headers: headersBuilder?.call(),
      );
      if (_stopped) {
        unawaited(socket.close());
        return;
      }
      _socket = socket;
      _attempt = 0;
      _lastMessageAt = DateTime.now();
      _startHeartbeat();
      _subscription = socket.listen(
        _onMessage,
        onDone: _scheduleReconnect,
        onError: (_) => _scheduleReconnect(),
        cancelOnError: true,
      );
      _connectedController.add(null);
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _onMessage(dynamic raw) {
    if (raw is! String) return;
    _lastMessageAt = DateTime.now();
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return;
      final event = '${decoded['event'] ?? ''}';
      if (event.isEmpty || event == 'connected' || event == 'pong') return;
      final payload = decoded['payload'];
      _eventsController.add(
        RealtimeEvent(
          event,
          payload is Map<String, dynamic> ? payload : const {},
        ),
      );
    } on FormatException {
      // Mensagem malformada: ignora e mantém a conexão.
    }
  }

  void _scheduleReconnect() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _socket = null;
    _subscription = null;
    if (_stopped) return;
    final index = _attempt.clamp(0, _backoffSeconds.length - 1);
    _attempt++;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(
      Duration(seconds: _backoffSeconds[index]),
      () => unawaited(_connect()),
    );
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      final socket = _socket;
      final lastMessageAt = _lastMessageAt;
      if (socket == null || lastMessageAt == null) return;
      if (DateTime.now().difference(lastMessageAt) >
          const Duration(seconds: 50)) {
        unawaited(socket.close(4000, 'heartbeat timeout'));
        return;
      }
      socket.add(jsonEncode({'event': 'ping'}));
    });
  }
}
