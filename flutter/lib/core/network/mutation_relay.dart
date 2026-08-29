import 'relay_origin.dart';

/// A mutation that may be handed to a trusted StarChef node on the local LAN.
class RelayMutation {
  const RelayMutation({
    required this.method,
    required this.path,
    required this.operationId,
    this.query,
    this.body,
    this.origin,
    this.sealedOrigin = '',
  });

  final String method;
  final String path;
  final String operationId;
  final Map<String, dynamic>? query;
  final Map<String, dynamic>? body;

  /// Credenciais de quem originou a operação.
  ///
  /// No cliente é o que se envia; no principal é o que se recupera do envelope
  /// para encaminhar em nome de quem pediu. Nunca é serializado em claro — ver
  /// [sealedOrigin].
  final RelayOrigin? origin;

  /// A origem cifrada com a chave de pareamento (o que trafega de fato).
  ///
  /// A rede local é autenticada, mas não é criptografada: um token em claro
  /// no corpo ficaria legível para qualquer um com acesso ao segmento. O lacre
  /// é aberto só por quem tem a chave — e a assinatura do corpo, que já
  /// existe, garante que ninguém o trocou no caminho.
  final String sealedOrigin;

  RelayMutation copyWith({
    String? path,
    Map<String, dynamic>? body,
    RelayOrigin? origin,
  }) => RelayMutation(
    method: method,
    path: path ?? this.path,
    operationId: operationId,
    query: query,
    body: body ?? this.body,
    origin: origin ?? this.origin,
    sealedOrigin: sealedOrigin,
  );

  Map<String, dynamic> toJson() => {
    'method': method,
    'path': path,
    'operation_id': operationId,
    'query': ?query,
    'body': ?body,
    if (sealedOrigin.isNotEmpty) 'origin': sealedOrigin,
  };
}

/// Optional principal-first route used by a client checkout.
///
/// The principal owns cloud delivery and its durable outbox for mutations it
/// accepts. If it is definitively unavailable, the caller may still use the
/// cloud or its own local outbox.
abstract interface class MutationRelay {
  Future<Map<String, dynamic>> relay(RelayMutation mutation);

  /// O Caixa Principal responde agora?
  ///
  /// A fila do caixa secundário consulta isto antes de gastar tentativas: sem
  /// a checagem, um ciclo com o principal desligado levaria o backoff de cada
  /// operação ao teto sem nenhuma chance real de entrega — exatamente o mesmo
  /// motivo pelo qual o principal consulta a saúde do backend.
  Future<bool> probe();

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
