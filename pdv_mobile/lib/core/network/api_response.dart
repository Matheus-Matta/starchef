import 'dart:convert';

import 'api_exception.dart';

Map<String, dynamic> decodeApiResponse(int statusCode, String body) {
  Object? decoded;
  try {
    decoded = body.isEmpty ? const <String, dynamic>{} : jsonDecode(body);
  } on FormatException {
    if (statusCode >= 200 && statusCode < 300) {
      return <String, dynamic>{'value': body};
    }
  }
  final map = decoded is Map
      ? Map<String, dynamic>.from(decoded)
      : <String, dynamic>{'results': decoded};
  if (statusCode >= 200 && statusCode < 300) return map;
  throw ApiException(extractApiDetail(map), statusCode: statusCode);
}

String extractApiDetail(Map<String, dynamic> payload) {
  final error = payload['error'];
  if (error is Map) {
    final message = error['message'];
    if (message is String && message.trim().isNotEmpty) return message;
    if (message is Map && message['detail'] != null) {
      return '${message['detail']}';
    }
    if (error['detail'] != null) return '${error['detail']}';
  }
  if (payload['detail'] != null) return '${payload['detail']}';
  if (payload.isNotEmpty) {
    final first = payload.entries.first;
    final value = first.value;
    if (value is List && value.isNotEmpty) return '${value.first}';
    return '${first.key}: $value';
  }
  return 'Não foi possível concluir a operação.';
}
