class PendingMutation {
  const PendingMutation({
    required this.operationId,
    required this.method,
    required this.path,
    required this.kind,
    required this.summary,
    required this.createdAt,
    this.body,
    this.placeholderOrderId,
    this.attempts = 0,
    this.lastError,
  });

  final String operationId;
  final String method;
  final String path;
  final Map<String, dynamic>? body;
  final String kind;
  final String summary;
  final DateTime createdAt;
  final String? placeholderOrderId;
  final int attempts;
  final String? lastError;

  /// O ATENDIMENTO a que esta operação pertence — um pedido ou uma comanda.
  ///
  /// Os dois entram aqui porque a tela de detalhe é a mesma para os dois, e é
  /// por este id que ela acha o que ainda está na fila. Enquanto só `/orders/`
  /// era reconhecido, a anotação que o garçom lançava sem rede subia
  /// normalmente mas não aparecia em lugar nenhum da comanda: sem selo de
  /// "aguardando conexão", e — pior — sem a lista de recusados, então um item
  /// que o backend rejeitasse sumia da tela sem deixar rastro.
  String? get subjectId {
    if (placeholderOrderId != null) return placeholderOrderId;
    return _subjectPath.firstMatch(path)?.group(1);
  }

  String? get itemId => _itemPath.firstMatch(path)?.group(1);

  static final _subjectPath = RegExp(r'^/(?:orders|commands)/([^/]+)/');
  static final _itemPath = RegExp(
    r'^/(?:orders|commands)/[^/]+/items/([^/]+)/',
  );

  PendingMutation withOrderIdReplaced(String placeholder, String realId) =>
      PendingMutation(
        operationId: operationId,
        method: method,
        path: path.replaceAll(placeholder, realId),
        body: body,
        kind: kind,
        summary: summary,
        createdAt: createdAt,
        placeholderOrderId: placeholderOrderId,
        attempts: attempts,
        lastError: lastError,
      );

  Map<String, dynamic> toJson() => {
    'operation_id': operationId,
    'method': method,
    'path': path,
    'body': body,
    'kind': kind,
    'summary': summary,
    'created_at': createdAt.toIso8601String(),
    if (placeholderOrderId != null) 'placeholder_order_id': placeholderOrderId,
    'attempts': attempts,
    'last_error': lastError,
  };

  static PendingMutation fromJson(Map<String, dynamic> json) => PendingMutation(
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
    placeholderOrderId: json['placeholder_order_id'] as String?,
    attempts: (json['attempts'] as num?)?.toInt() ?? 0,
    lastError: json['last_error'] as String?,
  );
}

class FailedMutation {
  const FailedMutation({required this.mutation, required this.reason});

  final PendingMutation mutation;
  final String reason;
  String? get subjectId => mutation.subjectId;

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
