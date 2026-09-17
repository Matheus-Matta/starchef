import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'api_response.dart';

typedef TokensChanged = Future<void> Function(String access, String refresh);

class ApiClient {
  ApiClient({required this.baseUrlProvider, http.Client? httpClient})
    : _http = httpClient ?? http.Client();

  static const _timeout = Duration(seconds: 15);
  final String Function() baseUrlProvider;
  final http.Client _http;

  String? _accessToken;
  String? _refreshToken;
  String? _terminalId;
  TokensChanged? _onTokensChanged;
  Future<bool>? _refreshInFlight;

  String get baseUrl => baseUrlProvider();
  String? get currentAccessToken => _accessToken;

  void configureSession({
    required String accessToken,
    required String refreshToken,
    required String terminalId,
    TokensChanged? onTokensChanged,
  }) {
    _accessToken = accessToken;
    _refreshToken = refreshToken;
    _terminalId = terminalId;
    _onTokensChanged = onTokensChanged;
  }

  void clearSession() {
    _accessToken = null;
    _refreshToken = null;
    _onTokensChanged = null;
  }

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) => request('GET', path, query: query, accessToken: accessToken);

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
    String? idempotencyKey,
  }) => request(
    'POST',
    path,
    body: body,
    accessToken: accessToken,
    idempotencyKey: idempotencyKey,
  );

  Future<Map<String, dynamic>> patch(
    String path, {
    Map<String, dynamic>? body,
    String? idempotencyKey,
  }) => request('PATCH', path, body: body, idempotencyKey: idempotencyKey);

  Future<Map<String, dynamic>> delete(
    String path, {
    Map<String, dynamic>? body,
    String? idempotencyKey,
  }) => request('DELETE', path, body: body, idempotencyKey: idempotencyKey);

  Future<Map<String, dynamic>> request(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? accessToken,
    String? idempotencyKey,
  }) async {
    final explicitToken = accessToken != null;
    try {
      return await _send(
        method,
        path,
        query: query,
        body: body,
        token: accessToken ?? _accessToken,
        idempotencyKey: idempotencyKey,
      );
    } on ApiException catch (error) {
      final canRefresh =
          error.statusCode == 401 &&
          !explicitToken &&
          !path.startsWith('/auth/') &&
          (_refreshToken?.isNotEmpty ?? false);
      if (!canRefresh || !await _refresh()) rethrow;
      return _send(
        method,
        path,
        query: query,
        body: body,
        token: _accessToken,
        idempotencyKey: idempotencyKey,
      );
    }
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? token,
    String? idempotencyKey,
  }) async {
    final uri = Uri.parse('$baseUrl$path').replace(
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
    final request = http.Request(method, uri)
      ..headers['accept'] = 'application/json';
    if (token?.isNotEmpty ?? false) {
      request.headers['authorization'] = 'Bearer $token';
    }
    if (_terminalId?.isNotEmpty ?? false) {
      request.headers['X-Terminal-Id'] = _terminalId!;
      request.headers['X-Terminal-Name'] = 'PDV Mobile';
    }
    if (idempotencyKey?.isNotEmpty ?? false) {
      request.headers['Idempotency-Key'] = idempotencyKey!;
    }
    if (body != null) {
      request.headers['content-type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    try {
      final streamed = await _http.send(request).timeout(_timeout);
      final response = await http.Response.fromStream(streamed);
      return decodeApiResponse(response.statusCode, response.body);
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

  Future<bool> _refresh() {
    final current = _refreshInFlight;
    if (current != null) return current;
    final future = _performRefresh();
    _refreshInFlight = future;
    return future.whenComplete(() => _refreshInFlight = null);
  }

  Future<bool> _performRefresh() async {
    try {
      final response = await _send(
        'POST',
        '/auth/refresh/',
        body: {'refresh': _refreshToken, 'no_cookie': true},
      );
      final access = '${response['access'] ?? ''}';
      final refresh = '${response['refresh'] ?? _refreshToken ?? ''}';
      if (access.isEmpty) return false;
      _accessToken = access;
      _refreshToken = refresh;
      await _onTokensChanged?.call(access, refresh);
      return true;
    } on ApiException {
      return false;
    }
  }

  static Map<String, dynamic> decodeResponse(int status, String body) =>
      decodeApiResponse(status, body);

  static String extractDetail(Map<String, dynamic> payload) =>
      extractApiDetail(payload);

  void close() => _http.close();
}
