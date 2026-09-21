import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'api_exception.dart';
import 'cloud_fallback.dart';
import 'api_response.dart';

part 'api_client_fallback.dart';
part 'api_client_transport.dart';

typedef TokensChanged = Future<void> Function(String access, String refresh);

class ApiClient {
  ApiClient({required this.baseUrlProvider, http.Client? httpClient})
    : _http = httpClient ?? http.Client();

  static const _timeout = Duration(seconds: 15);
  final String Function() baseUrlProvider;

  /// A nuvem como SEGUNDO servidor, quando o backend da loja não responde.
  final CloudFallback cloudFallback = CloudFallback();

  /// De onde veio a última resposta que chegou à tela.
  ServerOrigin lastServerOrigin = ServerOrigin.loja;
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
    return _comPlanoB(
      method,
      path,
      query: query,
      body: body,
      accessToken: accessToken,
      idempotencyKey: idempotencyKey,
    );
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
