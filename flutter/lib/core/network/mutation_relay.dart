/// A mutation that may be handed to a trusted StarChef node on the local LAN.
class RelayMutation {
  const RelayMutation({
    required this.method,
    required this.path,
    required this.operationId,
    this.query,
    this.body,
  });

  final String method;
  final String path;
  final String operationId;
  final Map<String, dynamic>? query;
  final Map<String, dynamic>? body;

  Map<String, dynamic> toJson() => {
    'method': method,
    'path': path,
    'operation_id': operationId,
    'query': ?query,
    'body': ?body,
  };
}

/// Optional principal-first route used by a client checkout.
///
/// The principal owns cloud delivery and its durable outbox for mutations it
/// accepts. If it is definitively unavailable, the caller may still use the
/// cloud or its own local outbox.
abstract interface class MutationRelay {
  Future<Map<String, dynamic>> relay(RelayMutation mutation);

  /// Lê pelo Caixa Principal, que responde do próprio armazenamento local.
  ///
  /// É o que faz o secundário enxergar a mesma verdade que o principal. Sem
  /// isso ele lia direto da nuvem: com a internet fora e a rede local de pé —
  /// a falha mais comum — ele conseguia gravar pelo principal, mas não
  /// conseguia abrir o pedido que ia alterar.
  Future<Map<String, dynamic>> read(RelayRead request);
}

/// Uma leitura encaminhada ao Caixa Principal.
class RelayRead {
  const RelayRead({required this.path, this.query});

  final String path;
  final Map<String, dynamic>? query;

  Map<String, dynamic> toJson() => {'path': path, 'query': ?query};
}

/// The principal node was definitively unreachable before delivery.
///
/// In this case the caller may safely keep the mutation in its own outbox.
class MutationRelayUnavailable implements Exception {
  const MutationRelayUnavailable(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Delivery may have happened, but its acknowledgement could not be proven.
///
/// The caller must not create a second local copy because that could duplicate
/// a sale after reconnection.
class MutationRelayUncertain implements Exception {
  const MutationRelayUncertain(this.message);

  final String message;

  @override
  String toString() => message;
}
