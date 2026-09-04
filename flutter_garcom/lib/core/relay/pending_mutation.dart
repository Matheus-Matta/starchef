/// Uma gravação que não chegou ao Caixa Principal e está esperando a conexão
/// voltar para ser reenviada.
///
/// O [operationId] é gerado UMA VEZ, na primeira tentativa, e reutilizado em
/// todas as retentativas — é o que permite reenviar sem risco de duplicar: o
/// Caixa Principal guarda o recibo da primeira vez que aceitou esse id e
/// devolve o mesmo recibo se ele chegar de novo (mesmo mecanismo que o PDV
/// usa entre Caixa Cliente e Principal).
class PendingMutation {
  const PendingMutation({
    required this.operationId,
    required this.method,
    required this.path,
    required this.kind,
    required this.summary,
    required this.createdAt,
    this.body,
    this.attempts = 0,
    this.lastError,
    this.placeholderOrderId,
  });

  final String operationId;
  final String method;
  final String path;
  final Map<String, dynamic>? body;

  /// Categoria da operação (`add_item`, `void_item`, `send_to_kitchen`,
  /// `link_table`, `create_order`) — usada para agrupar/filtrar na UI (ex.:
  /// só as pendências de UM pedido, na tela de detalhe).
  final String kind;

  /// Texto pronto para mostrar ao garçom (ex.: "2x Coxinha").
  final String summary;

  final DateTime createdAt;
  final int attempts;
  final String? lastError;

  /// Id local (`offline-...`) atribuído a um pedido ainda não confirmado
  /// pelo caixa — só preenchido quando `kind == 'create_order'`. É o que
  /// permite a tela de detalhe abrir e acompanhar um pedido que ainda não
  /// tem id de verdade (ver [orderId] e `RelayGateway.resolvedOrderId`).
  final String? placeholderOrderId;

  /// Pedido a que esta operação pertence, quando aplicável (extraído do
  /// path, ou o id local desta própria criação). Usado para filtrar as
  /// pendências de UM pedido específico.
  String? get orderId {
    if (placeholderOrderId != null) return placeholderOrderId;
    final match = RegExp(r'^/orders/([^/]+)/').firstMatch(path);
    return match?.group(1);
  }

  /// Item alvo, quando esta operação é sobre um item específico (`add_item`
  /// não tem — o item ainda não existe; `void_item` tem).
  String? get itemId {
    final match = RegExp(r'^/orders/[^/]+/items/([^/]+)/').firstMatch(path);
    return match?.group(1);
  }

  PendingMutation retry({required String error}) => PendingMutation(
    operationId: operationId,
    method: method,
    path: path,
    body: body,
    kind: kind,
    summary: summary,
    createdAt: createdAt,
    attempts: attempts + 1,
    lastError: error,
    placeholderOrderId: placeholderOrderId,
  );

  /// Cópia com [placeholder] trocado por [realId] no path — usado quando uma
  /// criação de pedido enfileirada é confirmada e esta mutação (ex.: um item
  /// lançado nesse pedido enquanto ele ainda não tinha id real) ainda está na
  /// fila esperando ser enviada.
  PendingMutation withOrderIdReplaced(String placeholder, String realId) =>
      PendingMutation(
        operationId: operationId,
        method: method,
        path: path.replaceAll(placeholder, realId),
        body: body,
        kind: kind,
        summary: summary,
        createdAt: createdAt,
        attempts: attempts,
        lastError: lastError,
        placeholderOrderId: placeholderOrderId,
      );

  Map<String, dynamic> toJson() => {
    'operation_id': operationId,
    'method': method,
    'path': path,
    'body': body,
    'kind': kind,
    'summary': summary,
    'created_at': createdAt.toIso8601String(),
    'attempts': attempts,
    'last_error': lastError,
    if (placeholderOrderId != null) 'placeholder_order_id': placeholderOrderId,
  };

  static PendingMutation fromJson(Map<String, dynamic> json) =>
      PendingMutation(
        operationId: '${json['operation_id'] ?? ''}',
        method: '${json['method'] ?? ''}',
        path: '${json['path'] ?? ''}',
        body: json['body'] is Map
            ? Map<String, dynamic>.from(json['body'] as Map)
            : null,
        kind: '${json['kind'] ?? ''}',
        summary: '${json['summary'] ?? ''}',
        createdAt:
            DateTime.tryParse('${json['created_at'] ?? ''}') ?? DateTime.now(),
        attempts: (json['attempts'] as num?)?.toInt() ?? 0,
        lastError: json['last_error'] as String?,
        placeholderOrderId: json['placeholder_order_id'] as String?,
      );
}

/// Uma pendência que o Caixa Principal recusou de vez (erro de negócio, não de
/// conexão) — não é reenviada sozinha porque repetir devolveria o mesmo erro.
/// Fica visível até o garçom decidir descartar.
class FailedMutation {
  const FailedMutation({required this.mutation, required this.reason});

  final PendingMutation mutation;
  final String reason;

  /// Pedido a que a recusa pertence, para a tela de detalhe mostrá-la junto
  /// dos itens.
  String? get orderId => mutation.orderId;

  Map<String, dynamic> toJson() => {
    'mutation': mutation.toJson(),
    'reason': reason,
  };

  static FailedMutation fromJson(Map<String, dynamic> json) => FailedMutation(
    mutation: PendingMutation.fromJson(
      json['mutation'] is Map
          ? Map<String, dynamic>.from(json['mutation'] as Map)
          : const {},
    ),
    reason: '${json['reason'] ?? ''}',
  );
}
