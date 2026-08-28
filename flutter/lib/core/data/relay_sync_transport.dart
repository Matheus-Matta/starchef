import '../network/api_exception.dart';
import '../network/mutation_relay.dart';
import 'sync_service.dart';

/// Transporte da fila de um **Caixa Secundário**: o destino é o Caixa
/// Principal, nunca a nuvem (§8).
///
/// O secundário passa a ter a mesma arquitetura do principal — grava no
/// próprio SQLite, enfileira e entrega depois —, só que o "servidor" dele é o
/// principal da loja. Antes ele não tinha fila nenhuma: com o principal fora
/// do ar, cada operação era recusada na hora e o operador ficava sem vender
/// até alguém religar o outro computador.
///
/// A entrega ambígua ([MutationRelayUncertain]) é tratada como falha
/// temporária: o principal guarda um recibo por `operation_id`, então repetir
/// devolve a resposta original em vez de criar uma segunda venda. Insistir é
/// seguro; desistir perderia a operação.
class RelaySyncTransport implements SyncTransport {
  const RelaySyncTransport(this._relay);

  final MutationRelay _relay;

  @override
  Future<bool> ping() => _relay.probe();

  @override
  Future<Map<String, dynamic>> send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? idempotencyKey,
  }) async {
    try {
      if (method == 'GET') {
        return await _relay.read(RelayRead(path: path, query: query));
      }
      return await _relay.relay(
        RelayMutation(
          method: method,
          path: path,
          // A chave é a mesma da fila: é ela que o principal usa como recibo
          // para reconhecer uma repetição.
          operationId: idempotencyKey ?? '',
          query: query,
          body: body,
        ),
      );
    } on MutationRelayUnavailable catch (error) {
      throw TransientSyncFailure(
        'O Caixa Principal não respondeu. ${error.message}',
      );
    } on MutationRelayUncertain catch (error) {
      throw TransientSyncFailure(
        'A confirmação do Caixa Principal foi interrompida. ${error.message}',
        offline: false,
      );
    } on ApiException catch (error) {
      // O principal alcançou o servidor (ou a própria regra dele) e recusou.
      // Repetir daria o mesmo resultado; isto é uma pendência para revisão.
      if (error.isConnectivity) {
        throw TransientSyncFailure(error.message);
      }
      rethrow;
    }
  }
}
