import 'dart:async';

import 'package:flutter/foundation.dart';

import '../network/api_client.dart';
import '../network/api_exception.dart';
import '../storage/offline_queue_store.dart';
import 'operation_id.dart';
import 'pending_mutation.dart';

part 'backend_gateway_flush.dart';

class MutationQueued implements Exception {
  const MutationQueued(this.mutation);
  final PendingMutation mutation;
}

class BackendGateway extends ChangeNotifier {
  BackendGateway({required this.api, required this.store});

  /// Pausa entre uma tentativa e a próxima. Curta: o garçom já saiu da
  /// tela e só espera ver o contador do topo zerar.
  static const _retryInterval = Duration(seconds: 3);

  /// Tentativas automáticas antes de a operação ir para "não enviados", onde
  /// o garçom vê o motivo e reenvia com um toque. Sem limite, um envio preso
  /// ficava girando para sempre, e o contador amarelo não dizia que era hora
  /// de agir.
  static const maxTentativas = 4;

  /// Chamado a cada operação que o servidor aceitou na fila — é por aqui que
  /// a impressão sabe que uma rodada enviada em segundo plano chegou.
  void Function(PendingMutation mutation)? onSent;
  final ApiClient api;
  final OfflineQueueStore store;
  final List<PendingMutation> _pending = [];
  final List<FailedMutation> _failed = [];
  final Map<String, String> _resolvedIds = {};

  Timer? _timer;
  bool _authenticated = false;
  bool _flushing = false;
  bool _restored = false;

  List<PendingMutation> get pending => List.unmodifiable(_pending);
  List<FailedMutation> get failed => List.unmodifiable(_failed);
  int get pendingCount => _pending.length;
  bool get flushing => _flushing;

  /// O que ainda está na fila para ESTE atendimento — pedido ou comanda.
  List<PendingMutation> pendingFor(String subjectId) =>
      _pending.where((item) => item.subjectId == subjectId).toList();
  List<FailedMutation> failedFor(String subjectId) =>
      _failed.where((item) => item.subjectId == subjectId).toList();
  String? resolvedOrderId(String placeholderId) => _resolvedIds[placeholderId];

  Future<void> restore() async {
    if (_restored) return;
    _restored = true;
    _pending.addAll(await store.load());
    _failed.addAll(await store.loadFailed());
    if (_pending.isNotEmpty || _failed.isNotEmpty) notifyListeners();
  }

  void setAuthenticated(bool value) {
    _authenticated = value;
    if (value && _pending.isNotEmpty) _scheduleFlush(immediate: true);
  }

  Future<Map<String, dynamic>> mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
    String? placeholderOrderId,
  }) async {
    if (!_authenticated) {
      throw const ApiException('Entre novamente para enviar alterações.');
    }
    final mutation = PendingMutation(
      operationId: OperationId.random(),
      method: method,
      path: path,
      kind: kind,
      summary: summary,
      body: body,
      createdAt: DateTime.now(),
      placeholderOrderId: placeholderOrderId,
    );
    try {
      return await _send(mutation);
    } on ApiException catch (error) {
      if (!error.isConnectivity) rethrow;
      await _enqueue(mutation);
      throw MutationQueued(mutation);
    }
  }

  /// Guarda a operação e devolve NA HORA; o envio corre em segundo plano.
  ///
  /// É o que libera o garçom: antes ele ficava parado olhando o carregando
  /// até o servidor responder (até 15 s por item com a rede ruim). A fila é
  /// a mesma de [mutate], persistida em disco, então fechar o app não perde
  /// nada — e é FIFO, então os itens chegam antes do "enviar à cozinha".
  Future<PendingMutation> enqueue({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
  }) async {
    if (!_authenticated) {
      throw const ApiException('Entre novamente para enviar alterações.');
    }
    final mutation = PendingMutation(
      operationId: OperationId.random(),
      method: method,
      path: path,
      kind: kind,
      summary: summary,
      body: body,
      createdAt: DateTime.now(),
    );
    await _enqueue(mutation, immediate: true);
    return mutation;
  }

  Future<Map<String, dynamic>> _send(PendingMutation mutation) => api.request(
    mutation.method,
    mutation.path,
    body: mutation.body,
    idempotencyKey: mutation.operationId,
  );

  Future<void> _enqueue(
    PendingMutation mutation, {
    bool immediate = false,
  }) async {
    _pending.add(mutation);
    await store.save(_pending);
    notifyListeners();
    _scheduleFlush(immediate: immediate);
  }

  void _scheduleFlush({bool immediate = false}) {
    _timer?.cancel();
    if (!_authenticated || _pending.isEmpty) return;
    _timer = Timer(immediate ? Duration.zero : _retryInterval, _flush);
  }

  Future<void> flushNow() => _flush();

  /// `notifyListeners` é protegido: o envio (`backend_gateway_flush.dart`)
  /// avisa a tela por aqui.
  void _avisar() => notifyListeners();

  void _resolveOrderId(String placeholder, String realId) {
    _resolvedIds[placeholder] = realId;
    for (var index = 0; index < _pending.length; index++) {
      _pending[index] = _pending[index].withOrderIdReplaced(
        placeholder,
        realId,
      );
    }
  }

  Future<void> retryFailed(String operationId) async {
    final index = _failed.indexWhere(
      (item) => item.mutation.operationId == operationId,
    );
    if (index < 0) return;
    // Reenviar à mão recomeça a contagem: são mais 4 tentativas, e não uma.
    final mutation = _failed.removeAt(index).mutation.semTentativas();
    await store.saveFailed(_failed);
    await _enqueue(mutation, immediate: true);
  }

  Future<void> discardFailed(String operationId) async {
    _failed.removeWhere((item) => item.mutation.operationId == operationId);
    await store.saveFailed(_failed);
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
