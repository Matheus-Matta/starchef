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

  String? get orderId {
    if (placeholderOrderId != null) return placeholderOrderId;
    return RegExp(r'^/orders/([^/]+)/').firstMatch(path)?.group(1);
  }

  String? get itemId =>
      RegExp(r'^/orders/[^/]+/items/([^/]+)/').firstMatch(path)?.group(1);

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
