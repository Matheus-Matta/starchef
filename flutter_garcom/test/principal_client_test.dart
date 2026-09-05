import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/network/api_exception.dart';
import 'package:starchef_garcom/core/relay/principal_client.dart';
import 'package:starchef_garcom/core/relay/relay_signature.dart';

/// Caixa Principal de mentira: fala o mesmo protocolo do PDV (verifica a
/// assinatura da requisição e assina a resposta), para o teste exercitar o
/// caminho completo — inclusive as recusas.
class FakePrincipal {
  FakePrincipal({required this.secret});

  final String secret;
  late final HttpServer _server;
  final List<Map<String, dynamic>> received = [];

  /// Quando definido, responde este status em vez de 200.
  int? failWithStatus;

  /// Assina a resposta com outro segredo — simula alguém se passando pelo
  /// principal na rede.
  String? impostorSecret;

  int get port => _server.port;

  Future<void> start() async {
    _server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _server.listen(_handle);
  }

  Future<void> stop() => _server.close(force: true);

  Future<void> _handle(HttpRequest request) async {
    final body = await utf8.decoder.bind(request).join();
    final nonce = request.headers.value('x-starchef-nonce') ?? '';
    final expected = RelaySignature.request(
      secret: secret,
      method: request.method,
      path: request.uri.toString(),
      timestamp:
          int.tryParse(request.headers.value('x-starchef-timestamp') ?? '') ??
          0,
      nonce: nonce,
      account: request.headers.value('x-starchef-account') ?? '',
      actor: request.headers.value('x-starchef-actor') ?? '',
      restaurant: request.headers.value('x-starchef-restaurant') ?? '',
      nodeId: request.headers.value('x-starchef-node') ?? '',
      body: body,
    );
    final signed = RelaySignature.constantTimeEquals(
      request.headers.value('x-starchef-signature') ?? '',
      expected,
    );

    received.add({
      'method': request.method,
      'path': request.uri.path,
      'body': body,
      'signed': signed,
      'nonce': nonce,
    });

    final status = !signed
        ? HttpStatus.unauthorized
        : (failWithStatus ?? HttpStatus.ok);
    final payload = switch (status) {
      HttpStatus.unauthorized => {'detail': 'Assinatura local inválida.'},
      HttpStatus.ok when request.uri.path == '/v1/health' => {'ok': true},
      HttpStatus.ok => {
        'ok': true,
        'result': {'id': 'pedido-1'},
      },
      _ => {'detail': 'O Caixa Principal recusou a operação.'},
    };
    final encoded = jsonEncode(payload);
    request.response
      ..statusCode = status
      ..headers.contentType = ContentType.json
      ..headers.set(
        'x-starchef-response-signature',
        RelaySignature.response(
          secret: impostorSecret ?? secret,
          requestNonce: nonce,
          statusCode: status,
          body: encoded,
        ),
      )
      ..write(encoded);
    await request.response.close();
  }
}

void main() {
  const secret = 'chave-de-pareamento-de-teste';
  const identity = RelayIdentity(
    accountId: 'conta-1',
    actorId: 'garcom-1',
    restaurantId: 'restaurante-1',
  );

  late FakePrincipal principal;
  late PrincipalClient client;
  late PrincipalConfig config;

  setUp(() async {
    principal = FakePrincipal(secret: secret);
    await principal.start();
    client = PrincipalClient();
    config = PrincipalConfig(
      host: '127.0.0.1',
      port: principal.port,
      secret: secret,
      nodeId: 'aparelho-de-teste',
    );
  });

  tearDown(() => principal.stop());

  test('health assinado é aceito pelo principal', () async {
    expect(await client.health(config, identity), isTrue);
    expect(principal.received.single['signed'], isTrue);
  });

  test('gravação chega como envelope de relay', () async {
    final result = await client.mutate(
      config,
      identity,
      method: 'POST',
      path: '/orders/pedido-1/items/',
      operationId: 'operacao-de-teste-1234',
      body: {'product': 'produto-1', 'quantity': 2},
    );

    expect(result['id'], 'pedido-1');
    final sent = principal.received.single;
    expect(sent['path'], '/v1/relay');
    final envelope = jsonDecode('${sent['body']}') as Map<String, dynamic>;
    expect(envelope['method'], 'POST');
    expect(envelope['path'], '/orders/pedido-1/items/');
    expect(envelope['operation_id'], 'operacao-de-teste-1234');
    expect(envelope['body'], {'product': 'produto-1', 'quantity': 2});
  });

  test('leitura vai pelo /v1/read com o caminho pedido', () async {
    await client.read(
      config,
      identity,
      path: '/orders/',
      query: {'status': 'open'},
    );

    final sent = principal.received.single;
    expect(sent['path'], '/v1/read');
    final envelope = jsonDecode('${sent['body']}') as Map<String, dynamic>;
    expect(envelope['path'], '/orders/');
    expect(envelope['query'], {'status': 'open'});
  });

  test('senha errada é recusada com a mensagem do principal', () async {
    final wrong = PrincipalConfig(
      host: config.host,
      port: config.port,
      secret: 'senha-errada',
      nodeId: config.nodeId,
    );

    // Com o segredo errado, nem a resposta pode ser autenticada — o app
    // precisa dizer "confira a senha", não "operação recusada".
    await expectLater(
      client.health(wrong, identity),
      throwsA(isA<PrincipalUnavailable>()),
    );
    expect(principal.received.single['signed'], isFalse);
  });

  test('resposta de um impostor na rede é rejeitada', () async {
    principal.impostorSecret = 'outra-chave-qualquer';

    await expectLater(
      client.health(config, identity),
      throwsA(isA<PrincipalUnavailable>()),
    );
  });

  test('recusa do principal vira ApiException com o status', () async {
    principal.failWithStatus = HttpStatus.conflict;

    await expectLater(
      client.mutate(
        config,
        identity,
        method: 'POST',
        path: '/orders/pedido-1/send-to-kitchen/',
        operationId: 'operacao-de-teste-1234',
      ),
      throwsA(
        isA<ApiException>().having(
          (error) => error.statusCode,
          'statusCode',
          HttpStatus.conflict,
        ),
      ),
    );
  });

  test('principal fora do ar não vira erro genérico', () async {
    await principal.stop();

    await expectLater(
      client.health(config, identity),
      throwsA(isA<PrincipalUnavailable>()),
    );
  });

  test('sessão incompleta nem chega a abrir conexão', () async {
    await expectLater(
      client.health(
        config,
        const RelayIdentity(
          accountId: 'conta-1',
          actorId: '',
          restaurantId: 'restaurante-1',
        ),
      ),
      throwsA(isA<PrincipalUnavailable>()),
    );
    expect(principal.received, isEmpty);
  });

  group('configuração do principal', () {
    PrincipalConfig build({
      String host = '192.168.0.10',
      int port = PrincipalConfig.defaultPort,
      String secret = 'chave',
    }) => PrincipalConfig(
      host: host,
      port: port,
      secret: secret,
      nodeId: 'aparelho',
    );

    test('aceita IP simples da rede da loja', () {
      expect(build().validate(), isEmpty);
    });

    test('recusa URL colada no lugar do IP', () {
      expect(build(host: 'http://192.168.0.10:47832').validate(), isNotEmpty);
    });

    test('recusa porta fora da faixa e senha vazia', () {
      expect(build(port: 80).validate(), isNotEmpty);
      expect(build(secret: '  ').validate(), isNotEmpty);
    });

    test('sobrevive a uma ida e volta pelo cofre', () {
      final original = build();
      final restored = PrincipalConfig.fromJson(original.toJson());
      expect(restored.host, original.host);
      expect(restored.port, original.port);
      expect(restored.secret, original.secret);
      expect(restored.nodeId, original.nodeId);
    });
  });
}
