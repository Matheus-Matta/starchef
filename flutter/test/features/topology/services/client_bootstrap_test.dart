import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/features/devices/services/local_device_agent.dart';
import 'package:starchef_pdv/features/topology/data/local_topology_store.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';
import 'package:starchef_pdv/features/topology/services/terminal_topology.dart';

/// A partida de um Caixa Secundário.
///
/// O caso que dá nome ao arquivo: o secundário nunca conectava no principal
/// enquanto o app do garçom, com o mesmo IP e a mesma chave, conectava na
/// primeira tentativa. A diferença não estava no protocolo — estava na ordem.
/// A rede local só era ligada depois que o PDV carregava restaurantes e
/// cardápio, e num secundário é o principal quem serve essas listas: sem
/// nuvem, a carga falhava, o relay nunca era ligado e o terminal passava o
/// expediente tentando reconectar sozinho.
void main() {
  const accountId = 'conta-1';
  const restaurantId = 'restaurante-1';

  late Directory temporaryDirectory;
  late ApiClient api;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'starchef-client-bootstrap-',
    );
    api = ApiClient(baseUrl: 'http://127.0.0.1:9/api/v1');
  });

  tearDown(() async {
    await api.dispose();
    try {
      await temporaryDirectory.delete(recursive: true);
    } on FileSystemException {
      // Limpeza é conveniência; o SQLite pode ainda estar fechando.
    }
  });

  LocalTopologyStore storeNamed(String name) => LocalTopologyStore(
    file: File(
      '${temporaryDirectory.path}${Platform.pathSeparator}$name.sqlite',
    ),
    secretStorage: _MemorySecretStorage(),
  );

  Future<int> freePort() async {
    final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = socket.port;
    await socket.close();
    return port;
  }

  Future<LocalTopologyService> startPrincipal({
    required String secret,
    required int port,
  }) async {
    final principal = LocalTopologyService(
      api: ApiClient(baseUrl: 'http://127.0.0.1:9/api/v1'),
      accessToken: 'token-principal',
      accountId: accountId,
      actorId: 'operador-do-caixa',
      restaurantId: restaurantId,
      store: storeNamed('principal'),
    );
    await principal.reconfigure(
      LocalTopologyConfig(
        mode: LocalTopologyMode.principal,
        nodeId: 'no-principal',
        port: port,
        pairingSecret: secret,
        trustedNetworkAcknowledged: true,
      ),
    );
    expect(principal.status.phase, LocalTopologyPhase.principalReady);
    return principal;
  }

  /// Espera a fase desejada sem depender do relógio: a reaplicação da
  /// configuração acontece fora da chamada que a disparou.
  Future<void> waitForPhase(
    LocalTopologyService service,
    LocalTopologyPhase phase,
  ) async {
    final deadline = DateTime.now().add(const Duration(seconds: 10));
    while (service.status.phase != phase && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 25));
    }
    expect(
      service.status.phase,
      phase,
      reason: 'status parou em "${service.status.message}"',
    );
  }

  test(
    'secundário sem unidade definida conecta quando o restaurante chega',
    () async {
      final secret = LocalTopologyStore.generatePairingSecret();
      final port = await freePort();
      final principal = await startPrincipal(secret: secret, port: port);
      addTearDown(principal.shutdown);

      // Como o PDV começa: papel e chave já gravados neste computador, mas a
      // unidade ainda desconhecida, porque ela vem do bootstrap de dados —
      // que, num secundário, depende deste mesmo principal.
      final client = LocalTopologyService(
        api: api,
        accessToken: 'token-cliente',
        accountId: accountId,
        actorId: 'operador-do-secundario',
        restaurantId: '',
        store: storeNamed('cliente'),
      );
      addTearDown(client.shutdown);
      await client.reconfigure(
        LocalTopologyConfig(
          mode: LocalTopologyMode.client,
          nodeId: 'no-secundario',
          principalHost: '127.0.0.1',
          port: port,
          pairingSecret: secret,
          trustedNetworkAcknowledged: true,
        ),
      );

      client.updateRestaurant(restaurantId);

      await waitForPhase(client, LocalTopologyPhase.clientReady);
      expect(await client.probe(), isTrue);
    },
    timeout: const Timeout(Duration(seconds: 30)),
  );

  test('a recusa do principal chega ao operador com o motivo', () async {
    final secret = LocalTopologyStore.generatePairingSecret();
    final port = await freePort();
    final principal = await startPrincipal(secret: secret, port: port);
    addTearDown(principal.shutdown);

    final client = LocalTopologyService(
      api: api,
      accessToken: 'token-cliente',
      accountId: accountId,
      actorId: 'operador-do-secundario',
      restaurantId: restaurantId,
      store: storeNamed('cliente'),
    );
    addTearDown(client.shutdown);
    await client.reconfigure(
      LocalTopologyConfig(
        mode: LocalTopologyMode.client,
        nodeId: 'no-secundario',
        principalHost: '127.0.0.1',
        port: port,
        pairingSecret: LocalTopologyStore.generatePairingSecret(),
        trustedNetworkAcknowledged: true,
      ),
    );

    // "Indisponível" sozinho mandava procurar cabo e roteador quando o
    // problema era a chave copiada errada.
    expect(client.status.phase, LocalTopologyPhase.unavailable);
    expect(client.status.message, contains('chave de pareamento'));
    expect(client.status.message, contains('Rede local'));
  }, timeout: const Timeout(Duration(seconds: 30)));

  group('TerminalTopology', () {
    test('liga a rede local antes de o PDV conhecer a unidade', () async {
      final deviceAgent = LocalDeviceAgent(api: api);
      addTearDown(deviceAgent.dispose);
      final topology = TerminalTopology(
        api: api,
        deviceAgent: deviceAgent,
        readIdentity: () => const TopologyIdentity(
          accessToken: 'token',
          accountId: accountId,
          actorId: 'operador',
          // Ainda sem unidade: é exatamente o instante em que o secundário
          // precisa do principal para carregar os dados.
        ),
        createStore: () => storeNamed('terminal'),
      );
      addTearDown(topology.shutdown);

      await topology.ensure();

      // Antes, a rede local só nascia depois da carga de dados — e num
      // secundário essa carga nunca terminava sem o principal.
      expect(topology.config, isNotNull);
    });

    test('não repete a partida quando chamada duas vezes', () async {
      final deviceAgent = LocalDeviceAgent(api: api);
      addTearDown(deviceAgent.dispose);
      final topology = TerminalTopology(
        api: api,
        deviceAgent: deviceAgent,
        readIdentity: () => const TopologyIdentity(
          accessToken: 'token',
          accountId: accountId,
          actorId: 'operador',
          restaurantId: restaurantId,
        ),
        createStore: () => storeNamed('terminal'),
      );
      addTearDown(topology.shutdown);

      await Future.wait([topology.ensure(), topology.ensure()]);
      final first = topology.service;
      await topology.ensure(restaurantId: restaurantId);

      expect(topology.service, same(first));
    });

    test('sem conta e operador, não há o que parear', () async {
      final deviceAgent = LocalDeviceAgent(api: api);
      addTearDown(deviceAgent.dispose);
      final topology = TerminalTopology(
        api: api,
        deviceAgent: deviceAgent,
        readIdentity: () =>
            const TopologyIdentity(accessToken: '', accountId: '', actorId: ''),
        createStore: () => storeNamed('terminal'),
      );
      addTearDown(topology.shutdown);

      await topology.ensure();

      expect(topology.service, isNull);
    });
  });
}

class _MemorySecretStorage implements TopologySecretStorage {
  String? _value;

  @override
  Future<String?> read() async => _value;

  @override
  Future<void> write(String value) async => _value = value;
}
