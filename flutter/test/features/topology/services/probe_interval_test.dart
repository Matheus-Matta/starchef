import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/features/topology/data/local_topology_store.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

class _MemorySecrets implements TopologySecretStorage {
  _MemorySecrets([this._value]);

  String? _value;

  @override
  Future<String?> read() async => _value;

  @override
  Future<void> write(String value) async => _value = value;
}

void main() {
  late Directory directory;
  var counter = 0;
  final services = <LocalTopologyService>[];
  final clients = <ApiClient>[];

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-probe');
  });

  tearDown(() async {
    for (final service in services) {
      await service.shutdown();
    }
    for (final client in clients) {
      await client.dispose();
    }
    services.clear();
    clients.clear();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  ApiClient apiWith([http.Client? transport]) {
    counter += 1;
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: transport,
      offlineStore: OfflineStore(
        file: File(
          '${directory.path}${Platform.pathSeparator}o-$counter.sqlite',
        ),
      ),
    );
    clients.add(api);
    return api;
  }

  LocalTopologyService serviceWith(ApiClient api, String secret) {
    counter += 1;
    final service = LocalTopologyService(
      api: api,
      accessToken: 'token',
      accountId: 'acc-1',
      actorId: 'user-1',
      restaurantId: 'rest-1',
      store: LocalTopologyStore(
        file: File(
          '${directory.path}${Platform.pathSeparator}t-$counter.sqlite',
        ),
        secretStorage: _MemorySecrets(secret),
      ),
    );
    services.add(service);
    return service;
  }

  /// Abre o Caixa Principal numa porta realmente livre.
  ///
  /// A porta era escolhida por `microsecond % 90`, sem checar se estava
  /// disponível: com três testes neste arquivo e outros arquivos abrindo
  /// servidores em paralelo, a colisão era questão de tempo — e o sintoma era
  /// um teste que falhava sozinho de vez em quando, tornando a suíte inútil
  /// justamente quando ela deveria acusar um problema real.
  Future<int> openPrincipal(
    LocalTopologyService principal,
    String secret,
  ) async {
    for (var attempt = 0; attempt < 5; attempt++) {
      final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final port = socket.port;
      await socket.close();
      await principal.reconfigure(
        LocalTopologyConfig(
          mode: LocalTopologyMode.principal,
          nodeId: LocalTopologyStore.generateNodeId(),
          port: port,
          pairingSecret: secret,
          trustedNetworkAcknowledged: true,
        ),
      );
      if (principal.status.phase == LocalTopologyPhase.principalReady) {
        return port;
      }
    }
    fail('Nenhuma porta livre para abrir o Caixa Principal do teste.');
  }

  test('sem o principal, o teste de conexão é frequente', () async {
    final service = serviceWith(
      apiWith(),
      LocalTopologyStore.generatePairingSecret(),
    );

    // O operador está impedido de lançar e esperando: cada segundo parado
    // é caixa parado.
    expect(service.status.phase, isNot(LocalTopologyPhase.clientReady));
    expect(service.probeInterval, const Duration(seconds: 3));
  });

  test('com o principal respondendo, o teste espaça e a leitura funciona', () async {
    final secret = LocalTopologyStore.generatePairingSecret();
    // Caixa Principal de verdade, servindo do próprio ApiClient.
    final principalApi = apiWith(
      MockClient(
        (_) async => http.Response(
          jsonEncode({
            'results': [
              {'id': 'order-1', 'sequence': 7},
            ],
          }),
          200,
          headers: {'content-type': 'application/json'},
        ),
      ),
    );
    final principal = serviceWith(principalApi, secret);
    final port = await openPrincipal(principal, secret);

    // Caixa secundário apontando para ele.
    final client = serviceWith(apiWith(), secret);
    await client.reconfigure(
      LocalTopologyConfig(
        mode: LocalTopologyMode.client,
        nodeId: LocalTopologyStore.generateNodeId(),
        principalHost: '127.0.0.1',
        port: port,
        pairingSecret: secret,
        trustedNetworkAcknowledged: true,
      ),
    );

    expect(client.status.phase, LocalTopologyPhase.clientReady);
    // Com a ligação de pé nada urgente depende do teste periódico: uma queda
    // entre dois deles é pega na hora da gravação, pelo teste sob demanda.
    expect(client.probeInterval, const Duration(seconds: 15));

    // E o secundário lê pelo principal, com o handshake assinado completo.
    final read = await client.read(const RelayRead(path: '/orders/'));
    expect((read['results'] as List).single['id'], 'order-1');
  });

  test('o ritmo volta a acelerar quando o principal cai', () async {
    final secret = LocalTopologyStore.generatePairingSecret();
    final principal = serviceWith(apiWith(MockClient((_) async {
      return http.Response('{}', 200, headers: {
        'content-type': 'application/json',
      });
    })), secret);
    final port = await openPrincipal(principal, secret);

    final client = serviceWith(apiWith(), secret);
    await client.reconfigure(
      LocalTopologyConfig(
        mode: LocalTopologyMode.client,
        nodeId: LocalTopologyStore.generateNodeId(),
        principalHost: '127.0.0.1',
        port: port,
        pairingSecret: secret,
        trustedNetworkAcknowledged: true,
      ),
    );
    expect(client.probeInterval, const Duration(seconds: 15));

    await principal.shutdown();
    await client.probe();

    // A recuperação precisa ser rápida porque o secundário não grava sem ele.
    expect(client.status.phase, LocalTopologyPhase.unavailable);
    expect(client.probeInterval, const Duration(seconds: 3));
  });
}
