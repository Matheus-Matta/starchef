import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/network/api_exception.dart';
import 'package:starchef_garcom/core/relay/principal_client.dart';
import 'package:starchef_garcom/core/relay/relay_gateway.dart';
import 'package:starchef_garcom/core/relay/relay_signature.dart';
import 'package:starchef_garcom/core/storage/offline_queue_store.dart';

/// A fila de reenvio: o pedido do usuário era "se perder conexão com o
/// caixa, salvar a alteração e ficar tentando reenviar quando o ping voltar".
/// Este arquivo testa exatamente esse comportamento — inclusive as duas
/// armadilhas que ele tem escondidas: não duplicar a operação quando a
/// resposta chega atrasada, e não insistir para sempre numa coisa que o caixa
/// recusou por motivo de negócio (não de rede).
void main() {
  const identity = RelayIdentity(
    accountId: 'conta-1',
    actorId: 'garcom-1',
    restaurantId: 'restaurante-1',
  );
  const secret = 'chave-de-pareamento';

  late _FakePrincipal principal;
  late RelayGateway gateway;
  late Directory tempDir;

  PrincipalConfig config() =>
      PrincipalConfig(host: '127.0.0.1', port: principal.port, secret: secret, nodeId: 'aparelho');

  setUp(() async {
    tempDir = Directory.systemTemp.createTempSync('starchef-garcom-gateway-');
    principal = _FakePrincipal(secret: secret);
    await principal.start();
    gateway = RelayGateway(
      client: PrincipalClient(),
      store: OfflineQueueStore(
        testFile: File('${tempDir.path}${Platform.pathSeparator}outbox.json'),
      ),
    );
    await gateway.restore();
    gateway.updateContext(config: config(), identity: identity);
  });

  tearDown(() async {
    gateway.dispose();
    await principal.stop();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('caixa disponível: envia direto, sem passar pela fila', () async {
    final result = await gateway.mutate(
      method: 'POST',
      path: '/orders/pedido-1/items/',
      kind: 'add_item',
      summary: '2x Coxinha',
      body: {'product': 'produto-1'},
    );

    expect(result['id'], 'pedido-1');
    expect(gateway.pendingCount, 0);
    expect(principal.received, hasLength(1));
  });

  test('caixa fora do ar: entra na fila e lança MutationQueued', () async {
    await principal.stop();

    await expectLater(
      gateway.mutate(
        method: 'POST',
        path: '/orders/pedido-1/items/',
        kind: 'add_item',
        summary: '2x Coxinha',
      ),
      throwsA(isA<MutationQueued>()),
    );

    expect(gateway.pendingCount, 1);
    expect(gateway.pending.single.summary, '2x Coxinha');
  });

  test('a pendência sobrevive a fechar e abrir o app', () async {
    await principal.stop();
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-1/items/', kind: 'add_item', summary: 'x')
        .catchError((_) => <String, dynamic>{});

    // Uma instância nova simula reabrir o app: lê o que ficou no disco.
    final reaberto = RelayGateway(client: PrincipalClient(), store: gateway.store);
    await reaberto.restore();

    expect(reaberto.pendingCount, 1);
    reaberto.dispose();
  });

  test('conexão volta: reenvia sozinho sem precisar de ação manual', () async {
    await principal.stop();
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-1/items/', kind: 'add_item', summary: 'x')
        .catchError((_) => <String, dynamic>{});
    expect(gateway.pendingCount, 1);

    await principal.start(port: 0);
    gateway.updateContext(config: config(), identity: identity);

    // O timer do gateway dispara sozinho; damos tempo para ele rodar em vez
    // de chamar flushNow(), que é justamente o caminho manual.
    await _waitUntil(() => gateway.pendingCount == 0, timeout: const Duration(seconds: 8));

    expect(principal.received, hasLength(1));
  });

  test('botão manual "tentar agora" também esvazia a fila', () async {
    await principal.stop();
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-1/items/', kind: 'add_item', summary: 'x')
        .catchError((_) => <String, dynamic>{});

    await principal.start(port: 0);
    gateway.updateContext(config: config(), identity: identity);
    await gateway.flushNow();

    expect(gateway.pendingCount, 0);
  });

  test('reenvio usa o MESMO operation_id — o caixa dedupe por ele', () async {
    await principal.stop();
    await gateway
        .mutate(
          method: 'POST',
          path: '/orders/pedido-1/items/',
          kind: 'add_item',
          summary: 'x',
        )
        .catchError((_) => <String, dynamic>{});
    final idNaFila = gateway.pending.single.operationId;

    await principal.start(port: 0);
    gateway.updateContext(config: config(), identity: identity);
    await gateway.flushNow();

    expect(principal.received.single['operation_id'], idNaFila);
  });

  test('ordem é preservada: item 2 não passa na frente do item 1', () async {
    await principal.stop();
    for (final rotulo in ['A', 'B', 'C']) {
      await gateway
          .mutate(
            method: 'POST',
            path: '/orders/pedido-1/items/',
            kind: 'add_item',
            summary: '1x $rotulo',
            body: {'label': rotulo},
          )
          .catchError((_) => <String, dynamic>{});
    }

    await principal.start(port: 0);
    gateway.updateContext(config: config(), identity: identity);
    await gateway.flushNow();

    expect(principal.receivedOrder, ['A', 'B', 'C']);
  });

  test('recusa de NEGÓCIO não entra na fila — falha na hora', () async {
    principal.rejectWith(statusCode: 409, detail: 'Pedido já fechado.');

    await expectLater(
      gateway.mutate(
        method: 'POST',
        path: '/orders/pedido-1/send-to-kitchen/',
        kind: 'send_to_kitchen',
        summary: 'Enviar pedido',
      ),
      throwsA(isA<ApiException>()),
    );

    expect(gateway.pendingCount, 0, reason: 'reenviar um 409 só repetiria o mesmo erro');
  });

  test('recusa de negócio DURANTE o reenvio vira pendência "recusada", não fica presa', () async {
    await principal.stop();
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-1/send-to-kitchen/', kind: 'send_to_kitchen', summary: 'Enviar')
        .catchError((_) => <String, dynamic>{});

    principal.rejectWith(statusCode: 409, detail: 'Pedido já foi fechado no caixa.');
    await principal.start(port: 0);
    gateway.updateContext(config: config(), identity: identity);
    await gateway.flushNow();

    expect(gateway.pendingCount, 0);
    expect(gateway.failed, hasLength(1));
    expect(gateway.failed.single.reason, contains('fechado'));
  });

  test('descartar uma pendência recusada a remove da lista', () async {
    // A recusa de negócio só entra em `failed` quando descoberta DURANTE o
    // reenvio (a recusa na hora já foi vista pelo garçom no ato). Por isso
    // enfileira primeiro (caixa fora do ar) e só então rejeita.
    await principal.stop();
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-1/send-to-kitchen/', kind: 'send_to_kitchen', summary: 'Enviar')
        .catchError((_) => <String, dynamic>{});

    principal.rejectWith(statusCode: 409, detail: 'Recusado.');
    await principal.start(port: 0);
    gateway.updateContext(config: config(), identity: identity);
    await gateway.flushNow();
    final id = gateway.failed.single.mutation.operationId;

    gateway.discardFailed(id);

    expect(gateway.failed, isEmpty);
  });

  test('pendingFor filtra por pedido — a tela de detalhe só vê as suas', () async {
    await principal.stop();
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-1/items/', kind: 'add_item', summary: 'x')
        .catchError((_) => <String, dynamic>{});
    await gateway
        .mutate(method: 'POST', path: '/orders/pedido-2/items/', kind: 'add_item', summary: 'y')
        .catchError((_) => <String, dynamic>{});

    expect(gateway.pendingFor('pedido-1'), hasLength(1));
    expect(gateway.pendingFor('pedido-2'), hasLength(1));
    expect(gateway.pendingFor('pedido-3'), isEmpty);
  });

  test(
    'pedido criado offline: resolve o id local quando a criação sincroniza',
    () async {
      await principal.stop();
      await expectLater(
        gateway.mutate(
          method: 'POST',
          path: '/orders/create-with-item/',
          kind: 'create_order',
          summary: 'Novo pedido',
          placeholderOrderId: 'offline-x',
        ),
        throwsA(isA<MutationQueued>()),
      );
      expect(gateway.resolvedOrderId('offline-x'), isNull);

      await principal.start(port: 0);
      gateway.updateContext(config: config(), identity: identity);
      await gateway.flushNow();

      expect(gateway.resolvedOrderId('offline-x'), 'pedido-1');
    },
  );

  test(
    'item lançado no pedido offline é reescrito com o id real antes de ser enviado',
    () async {
      await principal.stop();
      await gateway
          .mutate(
            method: 'POST',
            path: '/orders/create-with-item/',
            kind: 'create_order',
            summary: 'Novo pedido',
            placeholderOrderId: 'offline-x',
          )
          .catchError((_) => <String, dynamic>{});
      await gateway
          .mutate(
            method: 'POST',
            path: '/orders/offline-x/items/',
            kind: 'add_item',
            summary: '2x Coxinha',
          )
          .catchError((_) => <String, dynamic>{});
      expect(gateway.pendingCount, 2);

      await principal.start(port: 0);
      gateway.updateContext(config: config(), identity: identity);
      await gateway.flushNow();

      expect(gateway.pendingCount, 0);
      final paths = principal.received.map((e) => '${e['path']}').toList();
      expect(paths, ['/orders/create-with-item/', '/orders/pedido-1/items/']);
    },
  );

  test('sem pareamento nenhum, a operação recusa direto (sem travar)', () async {
    final semContexto = RelayGateway(
      client: PrincipalClient(),
      store: OfflineQueueStore(
        testFile: File('${tempDir.path}${Platform.pathSeparator}outro.json'),
      ),
    );

    await expectLater(
      semContexto.mutate(method: 'POST', path: '/orders/x/items/', kind: 'add_item', summary: 's'),
      throwsA(isA<PrincipalUnavailable>()),
    );
    expect(semContexto.pendingCount, 0);
    semContexto.dispose();
  });
}

Future<void> _waitUntil(bool Function() condition, {required Duration timeout}) async {
  final deadline = DateTime.now().add(timeout);
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) {
      fail('condição não atingida dentro de $timeout');
    }
    await Future<void>.delayed(const Duration(milliseconds: 100));
  }
}

/// Caixa Principal de mentira: fala o protocolo real (assina a resposta) e
/// pode ser desligado/religado na mesma porta para simular a queda de rede.
class _FakePrincipal {
  _FakePrincipal({required this.secret});

  final String secret;
  HttpServer? _server;
  int _lastPort = 0;
  int get port => _lastPort;

  final List<Map<String, dynamic>> received = [];
  final List<String> receivedOrder = [];

  int? _rejectStatus;
  String? _rejectDetail;

  void rejectWith({required int statusCode, required String detail}) {
    _rejectStatus = statusCode;
    _rejectDetail = detail;
  }

  Future<void> start({int port = 0}) async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, port == 0 ? _lastPort : port);
    _server = server;
    _lastPort = server.port;
    server.listen(_handle);
  }

  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }

  Future<void> _handle(HttpRequest request) async {
    final body = await utf8.decoder.bind(request).join();
    final decoded = body.isEmpty ? <String, dynamic>{} : Map<String, dynamic>.from(jsonDecode(body) as Map);
    received.add(decoded);
    final mutationBody = decoded['body'];
    if (mutationBody is Map && mutationBody['label'] != null) {
      receivedOrder.add('${mutationBody['label']}');
    }

    final status = _rejectStatus ?? HttpStatus.ok;
    final payload = jsonEncode(
      status == HttpStatus.ok
          ? {
              'ok': true,
              'result': {'id': 'pedido-1'},
            }
          : {'detail': _rejectDetail},
    );
    request.response
      ..statusCode = status
      ..headers.contentType = ContentType.json
      ..headers.set(
        'x-starchef-response-signature',
        RelaySignature.response(
          secret: secret,
          requestNonce: request.headers.value('x-starchef-nonce') ?? '',
          statusCode: status,
          body: payload,
        ),
      )
      ..write(payload);
    await request.response.close();
  }
}
