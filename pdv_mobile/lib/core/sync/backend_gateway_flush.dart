part of 'backend_gateway.dart';

/// O ENVIO da fila: em ordem, com no máximo [BackendGateway.maxTentativas]
/// tentativas por operação.
///
/// Fica separado porque é a regra que decide quando o garçom precisa agir: a
/// falha de rede tenta de novo sozinha; a recusa do servidor (400/409) e a
/// rede que não voltou depois das 4 tentativas vão para "não enviados", com o
/// motivo e o botão de reenviar.
extension _BackendGatewayFlush on BackendGateway {
  Future<void> _flush() async {
    if (_flushing || !_authenticated || _pending.isEmpty) return;
    _flushing = true;
    _avisar();
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
          _avisar();
          onSent?.call(mutation);
        } on ApiException catch (error) {
          if (error.isConnectivity) {
            final tentada = mutation.comTentativa(error.message);
            if (tentada.attempts < BackendGateway.maxTentativas) {
              // Para a rodada inteira: a próxima operação bateria na mesma
              // rede fora, e passar na frente quebraria a ordem (o "enviar à
              // cozinha" chegando antes dos itens).
              _pending[0] = tentada;
              await store.save(_pending);
              _avisar();
              break;
            }
            await _desistir(
              tentada,
              'Não saiu em ${BackendGateway.maxTentativas} tentativas: '
              '${error.message}',
            );
            continue;
          }
          await _desistir(mutation, error.message);
        }
      }
    } finally {
      _flushing = false;
      _avisar();
      _scheduleFlush();
    }
  }

  Future<void> _desistir(PendingMutation mutation, String motivo) async {
    _pending.removeAt(0);
    _failed.add(FailedMutation(mutation: mutation, reason: motivo));
    await store.save(_pending);
    await store.saveFailed(_failed);
    _avisar();
  }
}
