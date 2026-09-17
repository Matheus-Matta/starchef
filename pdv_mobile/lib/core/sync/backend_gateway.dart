import 'dart:async';

import 'package:flutter/foundation.dart';

import '../network/api_client.dart';
import '../network/api_exception.dart';
import '../storage/offline_queue_store.dart';
import 'operation_id.dart';
import 'pending_mutation.dart';

class MutationQueued implements Exception {
  const MutationQueued(this.mutation);
  final PendingMutation mutation;
}

class BackendGateway extends ChangeNotifier {
  BackendGateway({required this.api, required this.store});

  static const _retryInterval = Duration(seconds: 5);
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

  List<PendingMutation> pendingFor(String orderId) =>
      _pending.where((item) => item.orderId == orderId).toList();
  List<FailedMutation> failedFor(String orderId) =>
      _failed.where((item) => item.orderId == orderId).toList();
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

  Future<Map<String, dynamic>> _send(PendingMutation mutation) => api.request(
    mutation.method,
    mutation.path,
    body: mutation.body,
    idempotencyKey: mutation.operationId,
  );

  Future<void> _enqueue(PendingMutation mutation) async {
    _pending.add(mutation);
    await store.save(_pending);
    notifyListeners();
    _scheduleFlush();
  }

  void _scheduleFlush({bool immediate = false}) {
    _timer?.cancel();
    if (!_authenticated || _pending.isEmpty) return;
    _timer = Timer(immediate ? Duration.zero : _retryInterval, _flush);
  }

  Future<void> flushNow() => _flush();

  Future<void> _flush() async {
    if (_flushing || !_authenticated || _pending.isEmpty) return;
    _flushing = true;
    notifyListeners();
    try {
      while (_pending.isNotEmpty) {
        final mutation = _pending.first;
        try {
          final response = await _send(mutation);
          _pending.removeAt(0);
          final placeholder = mutation.placeholderOrderId;
          if (mutation.kind == 'create_order' && placeholder != null) {
            final realId = '${response['id'] ?? ''}';
            if (realId.isNotEmpty) _resolveOrderId(placeholder, realId);
          }
          await store.save(_pending);
          notifyListeners();
        } on ApiException catch (error) {
          if (error.isConnectivity) break;
          _pending.removeAt(0);
          _failed.add(
            FailedMutation(mutation: mutation, reason: error.message),
          );
          await store.save(_pending);
          await store.saveFailed(_failed);
          notifyListeners();
        }
      }
    } finally {
      _flushing = false;
      notifyListeners();
      _scheduleFlush();
    }
  }

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
    final mutation = _failed.removeAt(index).mutation;
    await store.saveFailed(_failed);
    await _enqueue(mutation);
    _scheduleFlush(immediate: true);
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
