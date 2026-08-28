import 'dart:async';

import 'package:flutter/foundation.dart';

import '../network/api_exception.dart';
import '../storage/offline_queue_store.dart';
import 'pending_mutation.dart';
import 'principal_client.dart';
import 'relay_signature.dart';

/// Gravação aceita mas ainda não confirmada pelo Caixa Principal: entrou na
/// fila e será reenviada sozinha quando a conexão voltar.
///
/// Diferente de um erro: a UI que recebe isto deve seguir em frente (fechar o
/// formulário, mostrar o item como "pendente") em vez de mostrar uma falha.
class MutationQueued implements Exception {
  const MutationQueued(this.mutation);
  final PendingMutation mutation;
}

/// Fila de gravações com reenvio automático, entre o app e o Caixa Principal.
///
/// **Por que existe**: o salão é o lugar da loja com o Wi-Fi mais fraco. Uma
/// falha de rede no meio do lançamento de um item não pode virar "tente de
/// novo" pro garçom — o item fica salvo no aparelho e o app insiste sozinho.
///
/// **O que entra na fila**: só falhas de CONEXÃO (`PrincipalUnavailable`) —
/// o celular não alcançou o caixa, ou a resposta não veio a tempo. Uma
/// recusa de NEGÓCIO (`ApiException` com status, ex.: 409 porque o pedido já
/// foi fechado no caixa) nunca é enfileirada: reenviar um pedido rejeitado
/// simplesmente repetiria a rejeição para sempre. Essas vão para [failed],
/// visíveis até o garçom decidir descartar.
///
/// **Por que a ordem importa**: a fila é drenada uma operação de cada vez, na
/// ordem em que foram criadas. Lançar dois itens e cancelar o primeiro
/// enquanto offline só faz sentido reenviado nessa ordem.
class RelayGateway extends ChangeNotifier {
  RelayGateway({required this.client, required this.store});

  static const _retryInterval = Duration(seconds: 4);

  final PrincipalClient client;
  final OfflineQueueStore store;

  final List<PendingMutation> _pending = [];
  final List<FailedMutation> _failed = [];
  final Map<String, String> _resolvedIds = {};

  PrincipalConfig? _config;
  RelayIdentity? _identity;
  Timer? _timer;
  bool _flushing = false;
  bool _restored = false;

  List<PendingMutation> get pending => List.unmodifiable(_pending);
  List<FailedMutation> get failed => List.unmodifiable(_failed);
  int get pendingCount => _pending.length;
  bool get flushing => _flushing;

  /// Pendências de UM pedido — o que a tela de detalhe mostra sobrepondo os
  /// itens que já vieram do servidor.
  List<PendingMutation> pendingFor(String orderId) =>
      _pending.where((m) => m.orderId == orderId).toList();

  /// Id real que um pedido criado offline recebeu do caixa, uma vez que a
  /// criação (`kind == 'create_order'`) foi confirmada. `null` enquanto ainda
  /// não sincronizou — a tela de detalhe usa isto para trocar sozinha do id
  /// local para o real, sem esperar ação do garçom.
  String? resolvedOrderId(String placeholderId) => _resolvedIds[placeholderId];

  /// Lê a fila salva. Chamado uma vez, na abertura do app — depois disso o
  /// estado em memória é a fonte de verdade e cada mudança é persistida.
  Future<void> restore() async {
    if (_restored) return;
    _restored = true;
    _pending.addAll(await store.load());
    if (_pending.isNotEmpty) notifyListeners();
  }

  /// Atualiza o alvo do reenvio (conta/operador/restaurante e o caixa
  /// pareado). Chamado sempre que a sessão ou o pareamento mudam — sem isto,
  /// a fila tentaria reenviar contra um caixa ou uma sessão que não existe
  /// mais.
  void updateContext({
    required PrincipalConfig config,
    required RelayIdentity identity,
  }) {
    _config = config;
    _identity = identity;
    if (_pending.isNotEmpty) _scheduleFlush(immediate: true);
  }

  /// Envia agora; se o Caixa Principal estiver inalcançável, enfileira e
  /// lança [MutationQueued] em vez do erro de rede.
  Future<Map<String, dynamic>> mutate({
    required String method,
    required String path,
    required String kind,
    required String summary,
    Map<String, dynamic>? body,
    String? placeholderOrderId,
  }) async {
    final config = _config;
    final identity = _identity;
    if (config == null || identity == null) {
      throw const PrincipalUnavailable(
        'Nenhum Caixa Principal pareado com este aparelho.',
      );
    }
    final mutation = PendingMutation(
      operationId: RelaySignature.randomId(),
      method: method,
      path: path,
      body: body,
      kind: kind,
      summary: summary,
      createdAt: DateTime.now(),
      placeholderOrderId: placeholderOrderId,
    );
    try {
      return await _send(mutation, config, identity);
    } on PrincipalUnavailable {
      await _enqueue(mutation);
      throw MutationQueued(mutation);
    }
  }

  Future<Map<String, dynamic>> _send(
    PendingMutation mutation,
    PrincipalConfig config,
    RelayIdentity identity,
  ) => client.mutate(
    config,
    identity,
    method: mutation.method,
    path: mutation.path,
    operationId: mutation.operationId,
    body: mutation.body,
  );

  Future<void> _enqueue(PendingMutation mutation) async {
    _pending.add(mutation);
    await store.save(_pending);
    notifyListeners();
    _scheduleFlush();
  }

  void _scheduleFlush({bool immediate = false}) {
    _timer?.cancel();
    if (_pending.isEmpty) return;
    _timer = Timer(immediate ? Duration.zero : _retryInterval, _flush);
  }

  /// Tenta esvaziar a fila agora — usado pelo timer e pelo botão manual
  /// "Tentar agora" da UI.
  Future<void> flushNow() => _flush();

  Future<void> _flush() async {
    if (_flushing) return;
    final config = _config;
    final identity = _identity;
    if (config == null || identity == null || _pending.isEmpty) return;

    _flushing = true;
    notifyListeners();
    try {
      while (_pending.isNotEmpty) {
        final mutation = _pending.first;
        try {
          final response = await _send(mutation, config, identity);
          _pending.removeAt(0);
          final placeholderId = mutation.placeholderOrderId;
          if (mutation.kind == 'create_order' && placeholderId != null) {
            final realId = '${response['id'] ?? ''}';
            if (realId.isNotEmpty) _resolveOrderId(placeholderId, realId);
          }
          await store.save(_pending);
          notifyListeners();
        } on PrincipalUnavailable {
          // O caixa ainda não voltou: para aqui (preserva a ordem) e tenta de
          // novo daqui a pouco. Não adianta pular para o próximo — ele
          // também não vai conseguir.
          break;
        } on ApiException catch (error) {
          // O caixa respondeu e recusou: não é problema de conexão, então não
          // adianta insistir. Sai da fila e vira uma pendência visível.
          _pending.removeAt(0);
          _failed.add(FailedMutation(mutation: mutation, reason: error.message));
          await store.save(_pending);
          notifyListeners();
        }
      }
    } finally {
      _flushing = false;
      notifyListeners();
      _scheduleFlush();
    }
  }

  /// Um pedido criado offline acabou de ser confirmado: guarda o id real e
  /// reescreve, na própria fila ainda em memória, o path de qualquer
  /// mutação posterior que dependia do id local (ex.: um item lançado nesse
  /// pedido antes da criação sincronizar) — sem isso ela seria enviada
  /// referenciando um pedido que o caixa nunca vai reconhecer.
  void _resolveOrderId(String placeholderId, String realId) {
    _resolvedIds[placeholderId] = realId;
    for (var i = 0; i < _pending.length; i++) {
      _pending[i] = _pending[i].withOrderIdReplaced(placeholderId, realId);
    }
  }

  void discardFailed(String operationId) {
    _failed.removeWhere((item) => item.mutation.operationId == operationId);
    notifyListeners();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
