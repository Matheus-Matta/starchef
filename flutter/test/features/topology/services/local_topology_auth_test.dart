import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/features/topology/data/local_topology_store.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

/// Autenticação do relay no Caixa Principal.
///
/// O caso que dá nome ao arquivo: o app do garçom entra com o usuário DELE, e
/// o principal precisa aceitar. Antes, o principal exigia que o ator fosse o
/// mesmo usuário logado nele — o que só funcionava entre dois caixas operados
/// pela mesma pessoa e devolvia 401 para qualquer garçom.
void main() {
  const accountId = 'conta-1';
  const principalActor = 'operador-do-caixa';
  const restaurantId = 'restaurante-1';

  late Directory temporaryDirectory;
  late LocalTopologyService service;
  late String secret;
  late int port;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'starchef-relay-auth-',
    );
    final store = LocalTopologyStore(
      file: File(
        '${temporaryDirectory.path}${Platform.pathSeparator}topology.sqlite',
      ),
      secretStorage: _MemorySecretStorage(),
    );
    secret = LocalTopologyStore.generatePairingSecret();
    port = await _freePort();
    service = LocalTopologyService(
      api: ApiClient(baseUrl: 'http://127.0.0.1:9'),
      accessToken: 'token-do-principal',
      accountId: accountId,
      actorId: principalActor,
      restaurantId: restaurantId,
      store: store,
    );
    await service.reconfigure(
      LocalTopologyConfig(
        mode: LocalTopologyMode.principal,
        nodeId: 'caixa-principal',
        port: port,
        pairingSecret: secret,
        trustedNetworkAcknowledged: true,
      ),
    );
    expect(service.status.phase, LocalTopologyPhase.principalReady);
  });

  tearDown(() async {
    await service.shutdown();
    await _deleteTemporaryDirectory(temporaryDirectory);
  });

  Future<({int status, String detail})> health({
    required String actor,
    required String account,
    required String restaurant,
    String signingSecret = '',
    String nonce = 'nonce-do-aparelho-1',
    Duration clockSkew = Duration.zero,
  }) async {
    final timestamp =
        DateTime.now().toUtc().add(clockSkew).millisecondsSinceEpoch ~/ 1000;
    final signature = LocalRelayAuthenticator.signature(
      secret: signingSecret.isEmpty ? secret : signingSecret,
      method: 'GET',
      path: '/v1/health',
      timestamp: timestamp,
      nonce: nonce,
      account: account,
      actor: actor,
      restaurant: restaurant,
      nodeId: 'celular-do-garcom',
      body: '',
    );
    final client = HttpClient();
    try {
      final request = await client.getUrl(
        Uri.parse('http://127.0.0.1:$port/v1/health'),
      );
      request.headers
        ..set('x-starchef-timestamp', '$timestamp')
        ..set('x-starchef-nonce', nonce)
        ..set('x-starchef-node', 'celular-do-garcom')
        ..set('x-starchef-account', account)
        ..set('x-starchef-actor', actor)
        ..set('x-starchef-restaurant', restaurant)
        ..set('x-starchef-signature', signature);
      final response = await request.close();
      final body = await utf8.decoder.bind(response).join();
      final decoded = body.isEmpty ? const {} : jsonDecode(body) as Map;
      return (
        status: response.statusCode,
        detail: '${decoded['detail'] ?? ''}',
      );
    } finally {
      client.close(force: true);
    }
  }

  test('aceita um operador diferente do que está logado no principal', () async {
    final response = await health(
      actor: 'garcom-maria',
      account: accountId,
      restaurant: restaurantId,
    );

    expect(response.status, HttpStatus.ok);
  });

  test('continua aceitando o próprio operador do principal', () async {
    final response = await health(
      actor: principalActor,
      account: accountId,
      restaurant: restaurantId,
    );

    expect(response.status, HttpStatus.ok);
  });

  test('recusa outra conta dizendo que é outra conta', () async {
    final response = await health(
      actor: 'garcom-maria',
      account: 'conta-de-outra-loja',
      restaurant: restaurantId,
    );

    expect(response.status, HttpStatus.unauthorized);
    expect(response.detail, contains('outra conta'));
  });

  test('recusa outro restaurante dizendo que é outro restaurante', () async {
    final response = await health(
      actor: 'garcom-maria',
      account: accountId,
      restaurant: 'restaurante-2',
    );

    expect(response.status, HttpStatus.unauthorized);
    expect(response.detail, contains('outro restaurante'));
  });

  test('recusa requisição sem ator', () async {
    final response = await health(
      actor: '',
      account: accountId,
      restaurant: restaurantId,
    );

    expect(response.status, HttpStatus.unauthorized);
    expect(response.detail, contains('incompleta'));
  });

  test('recusa chave errada dizendo que é a chave', () async {
    final response = await health(
      actor: 'garcom-maria',
      account: accountId,
      restaurant: restaurantId,
      signingSecret: LocalTopologyStore.generatePairingSecret(),
    );

    expect(response.status, HttpStatus.unauthorized);
    expect(response.detail, contains('chave de pareamento'));
  });

  test('relógio fora de hora é apontado como relógio, não como senha', () async {
    final response = await health(
      actor: 'garcom-maria',
      account: accountId,
      restaurant: restaurantId,
      clockSkew: const Duration(minutes: 9),
    );

    expect(response.status, HttpStatus.unauthorized);
    expect(response.detail, contains('relógio'));
  });

  test('chave errada não revela nada sobre a loja', () async {
    // Sem a chave, o motivo tem de parar na própria chave: conta e restaurante
    // do caixa não podem vazar para quem só encostou na rede.
    final response = await health(
      actor: 'garcom-maria',
      account: 'conta-de-outra-loja',
      restaurant: 'restaurante-9',
      signingSecret: LocalTopologyStore.generatePairingSecret(),
    );

    expect(response.detail, contains('chave de pareamento'));
    expect(response.detail, isNot(contains('conta')));
    expect(response.detail, isNot(contains('restaurante')));
  });

  test('recusa o mesmo nonce duas vezes (proteção contra repetição)', () async {
    final first = await health(
      actor: 'garcom-maria',
      account: accountId,
      restaurant: restaurantId,
      nonce: 'nonce-repetido-123',
    );
    final second = await health(
      actor: 'garcom-maria',
      account: accountId,
      restaurant: restaurantId,
      nonce: 'nonce-repetido-123',
    );

    expect(first.status, HttpStatus.ok);
    expect(second.status, HttpStatus.unauthorized);
    expect(second.detail, contains('repetida'));
  });
}

Future<int> _freePort() async {
  final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
  final port = socket.port;
  await socket.close();
  return port;
}

Future<void> _deleteTemporaryDirectory(Directory directory) async {
  for (var attempt = 0; attempt < 5; attempt++) {
    try {
      if (await directory.exists()) {
        await directory.delete(recursive: true);
      }
      return;
    } on FileSystemException {
      await Future<void>.delayed(const Duration(milliseconds: 120));
    }
  }
}

class _MemorySecretStorage implements TopologySecretStorage {
  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async => this.value = value;
}
