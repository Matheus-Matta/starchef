import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../network/api_exception.dart';
import 'relay_signature.dart';

/// Endereço e credencial do Caixa Principal da loja.
class PrincipalConfig {
  const PrincipalConfig({
    required this.host,
    required this.port,
    required this.secret,
    required this.nodeId,
  });

  /// Mesma porta padrão do PDV (`LocalTopologyConfig.defaultPort`).
  static const defaultPort = 47832;

  final String host;
  final int port;
  final String secret;

  /// Identidade deste aparelho na rede local. Fica estável entre sessões para
  /// o principal reconhecer os recibos já entregues a ele.
  final String nodeId;

  String get endpoint => 'http://${host.trim()}:$port';

  Map<String, dynamic> toJson() => {
    'host': host,
    'port': port,
    'secret': secret,
    'node_id': nodeId,
  };

  static PrincipalConfig fromJson(Map<String, dynamic> json) => PrincipalConfig(
    host: '${json['host'] ?? ''}',
    port: int.tryParse('${json['port']}') ?? defaultPort,
    secret: '${json['secret'] ?? ''}',
    nodeId: '${json['node_id'] ?? ''}',
  );

  /// Problemas que impedem o aparelho de falar com o principal.
  List<String> validate() {
    final errors = <String>[];
    if (host.trim().isEmpty) {
      errors.add('Informe o IP do Caixa Principal.');
    } else if (!_isValidHost(host.trim())) {
      errors.add('Informe apenas o IP ou nome de rede, sem http:// nem porta.');
    }
    if (port < 1024 || port > 65535) {
      errors.add('A porta deve ficar entre 1024 e 65535.');
    }
    if (secret.trim().isEmpty) {
      errors.add('Informe a senha do Caixa Principal.');
    }
    return errors;
  }

  static bool _isValidHost(String value) =>
      value.isNotEmpty &&
      value.length <= 253 &&
      !value.contains(RegExp(r'[\s/:@?#\\]')) &&
      RegExp(r'^[A-Za-z0-9.-]+$').hasMatch(value) &&
      !value.startsWith('.') &&
      !value.endsWith('.') &&
      !value.contains('..');
}

/// Quem é o garçom, na visão do principal. Vai em cada requisição assinada.
class RelayIdentity {
  const RelayIdentity({
    required this.accountId,
    required this.actorId,
    required this.restaurantId,
  });

  final String accountId;
  final String actorId;
  final String restaurantId;

  bool get isComplete =>
      accountId.trim().isNotEmpty &&
      actorId.trim().isNotEmpty &&
      restaurantId.trim().isNotEmpty;
}

/// O Caixa Principal está fora do ar (ou recusou o pareamento).
class PrincipalUnavailable implements Exception {
  const PrincipalUnavailable(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Cliente do relay do Caixa Principal.
///
/// **Por que tudo passa por aqui**: quem fala com a impressora é o Caixa
/// Principal. Um celular não imprime na impressora USB do balcão, então o
/// pedido tirado no salão é entregue ao principal, que grava, imprime e
/// sincroniza com a nuvem. O app nunca escreve direto no backend.
///
/// O protocolo é o mesmo que o PDV usa entre Caixa Cliente e Caixa Principal:
/// HMAC-SHA256 por requisição (com timestamp e nonce contra repetição) e a
/// resposta também assinada, para o app saber que falou mesmo com o principal.
class PrincipalClient {
  PrincipalClient({HttpClient Function()? httpClientFactory})
    : _httpClientFactory = httpClientFactory ?? _defaultHttpClient;

  final HttpClient Function() _httpClientFactory;

  static HttpClient _defaultHttpClient() =>
      HttpClient()..connectionTimeout = const Duration(seconds: 3);

  /// O principal responde? Usado no pareamento e antes de cada gravação.
  Future<bool> health(PrincipalConfig config, RelayIdentity identity) async {
    final envelope = await send(
      config,
      identity,
      method: 'GET',
      path: '/v1/health',
    );
    return envelope['ok'] == true;
  }

  /// Leitura servida pelo principal (`/v1/read`).
  ///
  /// É o que faz o garçom enxergar exatamente o que o caixa enxerga, mesmo com
  /// a internet da loja fora: o principal responde do armazenamento dele.
  Future<Map<String, dynamic>> read(
    PrincipalConfig config,
    RelayIdentity identity, {
    required String path,
    Map<String, dynamic>? query,
  }) async {
    final envelope = await send(
      config,
      identity,
      method: 'POST',
      path: '/v1/read',
      body: {'path': path, 'query': ?query},
    );
    final result = envelope['result'];
    if (envelope['ok'] != true || result is! Map) {
      throw const ApiException(
        'Resposta de leitura inválida do Caixa Principal.',
      );
    }
    return Map<String, dynamic>.from(result);
  }

  /// Gravação encaminhada ao principal (`/v1/relay`).
  ///
  /// [operationId] identifica a operação de ponta a ponta: se a resposta se
  /// perder no caminho, repetir com o MESMO id devolve o recibo guardado no
  /// principal em vez de criar um segundo pedido.
  Future<Map<String, dynamic>> mutate(
    PrincipalConfig config,
    RelayIdentity identity, {
    required String method,
    required String path,
    required String operationId,
    Map<String, dynamic>? body,
  }) async {
    final envelope = await send(
      config,
      identity,
      method: 'POST',
      path: '/v1/relay',
      body: {
        'method': method.toUpperCase(),
        'path': path,
        'operation_id': operationId,
        'body': ?body,
      },
    );
    final result = envelope['result'];
    if (envelope['ok'] != true || result is! Map) {
      throw const ApiException(
        'Resposta de gravação inválida do Caixa Principal.',
      );
    }
    return Map<String, dynamic>.from(result);
  }

  /// Requisição assinada. Pública para o teste exercitar o protocolo inteiro.
  Future<Map<String, dynamic>> send(
    PrincipalConfig config,
    RelayIdentity identity, {
    required String method,
    required String path,
    Map<String, dynamic>? body,
  }) async {
    if (!identity.isComplete) {
      throw const PrincipalUnavailable(
        'A sessão não identifica conta, operador e restaurante para o '
        'pareamento.',
      );
    }
    final encodedBody = body == null ? '' : jsonEncode(body);
    final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
    final nonce = RelaySignature.randomId();
    final signature = RelaySignature.request(
      secret: config.secret,
      method: method,
      path: path,
      timestamp: timestamp,
      nonce: nonce,
      account: identity.accountId,
      actor: identity.actorId,
      restaurant: identity.restaurantId,
      nodeId: config.nodeId,
      body: encodedBody,
    );

    final client = _httpClientFactory();
    try {
      final request = await client
          .openUrl(method, Uri.parse('${config.endpoint}$path'))
          .timeout(const Duration(seconds: 4));
      request.headers
        ..set(HttpHeaders.acceptHeader, 'application/json')
        ..set('x-starchef-timestamp', '$timestamp')
        ..set('x-starchef-nonce', nonce)
        ..set('x-starchef-node', config.nodeId)
        ..set('x-starchef-account', identity.accountId)
        ..set('x-starchef-actor', identity.actorId)
        ..set('x-starchef-restaurant', identity.restaurantId)
        ..set('x-starchef-signature', signature);
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(encodedBody);
      }
      final response = await request.close().timeout(
        const Duration(seconds: 8),
      );
      final responseBody = await utf8.decoder.bind(response).join();

      // A resposta assinada prova que quem respondeu conhece a senha de
      // pareamento — sem isso, qualquer coisa na rede poderia se passar pelo
      // principal e "confirmar" um pedido que ninguém recebeu.
      final expected = RelaySignature.response(
        secret: config.secret,
        requestNonce: nonce,
        statusCode: response.statusCode,
        body: responseBody,
      );
      final received =
          response.headers.value('x-starchef-response-signature') ?? '';
      if (!RelaySignature.constantTimeEquals(received, expected)) {
        throw const PrincipalUnavailable(
          'A resposta não pôde ser autenticada: confira a senha do Caixa '
          'Principal.',
        );
      }

      final decoded = responseBody.isEmpty
          ? const <String, dynamic>{}
          : jsonDecode(responseBody);
      final result = decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{};
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ApiException(
          '${result['detail'] ?? 'O Caixa Principal recusou a operação.'}',
          statusCode: response.statusCode,
        );
      }
      return result;
    } on ApiException {
      rethrow;
    } on PrincipalUnavailable {
      rethrow;
    } on TimeoutException {
      throw PrincipalUnavailable(
        'O Caixa Principal ${config.host}:${config.port} não respondeu.',
      );
    } on SocketException {
      throw PrincipalUnavailable(
        'Não foi possível alcançar ${config.host}:${config.port}. '
        'Confira se o aparelho está no Wi-Fi da loja.',
      );
    } finally {
      client.close(force: true);
    }
  }
}
