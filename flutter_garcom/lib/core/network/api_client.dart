import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

/// Cliente HTTP do backend (Retaguarda).
///
/// O app do garçom usa o backend para DUAS coisas: validar o login e ler o
/// catálogo/pedidos quando o Caixa Principal não está no ar. Toda ESCRITA vai
/// pelo Caixa Principal — é ele que imprime (ver [PrincipalClient]).
class ApiClient {
  ApiClient({required this.baseUrl, http.Client? httpClient})
    : _http = httpClient ?? http.Client();

  final String baseUrl;
  final http.Client _http;

  static const _timeout = Duration(seconds: 12);

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) => _send('GET', path, query: query, accessToken: accessToken);

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
  }) => _send('POST', path, body: body, accessToken: accessToken);

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
    final request = http.Request(method, uri)
      ..headers['accept'] = 'application/json';
    if (accessToken != null && accessToken.isNotEmpty) {
      request.headers['authorization'] = 'Bearer $accessToken';
    }
    if (body != null) {
      request.headers['content-type'] = 'application/json';
      request.body = jsonEncode(body);
    }

    try {
      final streamed = await _http.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(streamed);
      return decodeResponse(response.statusCode, response.body);
    } on TimeoutException {
      throw const ApiException(
        'O servidor demorou demais para responder.',
        isConnectivity: true,
      );
    } on SocketException catch (error) {
      throw ApiException(
        'Sem conexão com o servidor (${error.message}).',
        isConnectivity: true,
      );
    } on http.ClientException catch (error) {
      throw ApiException(error.message, isConnectivity: true);
    }
  }

  /// Traduz corpo + status em dados ou erro. Exposto para teste.
  static Map<String, dynamic> decodeResponse(int statusCode, String body) {
    final decoded = body.isEmpty ? const <String, dynamic>{} : jsonDecode(body);
    final map = decoded is Map
        ? Map<String, dynamic>.from(decoded)
        : <String, dynamic>{'results': decoded};
    if (statusCode >= 200 && statusCode < 300) return map;
    throw ApiException(extractDetail(map), statusCode: statusCode);
  }

  /// O backend responde erros em dois formatos: o envelope padronizado
  /// (`error.message`, ver apps/core/exceptions.py) e o `detail` cru do DRF.
  static String extractDetail(Map<String, dynamic> payload) {
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
      final text = value is List && value.isNotEmpty
          ? '${value.first}'
          : '$value';
      return '${first.key}: $text';
    }
    return 'Não foi possível concluir a operação.';
  }

  void close() => _http.close();
}
