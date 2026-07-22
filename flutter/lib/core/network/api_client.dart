import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

class ApiClient {
  ApiClient({required this.baseUrl, http.Client? client})
    : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;

  Future<Map<String, dynamic>> post(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$baseUrl$path'),
        headers: {
          'Content-Type': 'application/json',
          if (accessToken != null) 'Authorization': 'Bearer $accessToken',
        },
        body: jsonEncode(body),
      );
      final decoded = response.body.isEmpty
          ? <String, dynamic>{}
          : jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;

      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiException(
          _messageFor(response.statusCode, decoded),
          statusCode: response.statusCode,
        );
      }
      return decoded;
    } on ApiException {
      rethrow;
    } on FormatException {
      throw const ApiException('A API retornou uma resposta inválida.');
    } on http.ClientException {
      throw const ApiException(
        'Não foi possível conectar à API. Verifique se o servidor está ativo.',
      );
    }
  }

  String _messageFor(int status, Map<String, dynamic> body) {
    if (status == 401) return 'Usuário ou senha inválidos.';
    if (status == 403) return 'Conta sem permissão para acessar o sistema.';
    final detail = body['detail'];
    return detail is String && detail.isNotEmpty
        ? detail
        : 'Não foi possível concluir a solicitação.';
  }
}
