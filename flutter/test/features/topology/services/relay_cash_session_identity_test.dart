import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';
import 'package:starchef_pdv/features/topology/data/local_topology_store.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

/// **O caixa que o Caixa Secundário lê tem que ser o dele, nunca o do Principal.**
///
/// O relato que deu origem a este arquivo: um terminal marcado como
/// secundário na rede local mostrava a sessão de caixa aberta no Principal,
/// mesmo depois de atualizar backend e PDV para as versões que já corrigiam a
/// regra de dono (`_belongsTo`/`opened_terminal_installation_id`). A regra
/// estava certa — o defeito era anterior a ela: `_serveRead` (o Principal
/// respondendo por uma leitura relayada) executava com a identidade AMBIENTE
/// deste terminal, e não com a de quem perguntou. A autenticação por
/// assinatura já sabia quem era (`_AuthenticatedNode`), mas essa identidade
/// morria antes de chegar em `RelayOrigin.current` — a mesma variável que
/// `_belongsTo` consulta para saber de quem é a sessão.
///
/// Estes testes sobem um Principal de verdade (SQLite + servidor HTTP local)
/// e um ou mais Secundários de verdade (outra instância de
/// [LocalTopologyService], em modo cliente, conversando por socket real com
/// assinatura de pareamento) — nada aqui é simulado por chamada direta ao
/// gateway do lado do secundário, porque o bug só existe na travessia
/// HTTP/assinatura entre os dois.
void main() {
  const accountId = 'conta-1';
  const restaurantId = 'restaurante-1';

  late Directory temporaryDirectory;
  late String secret;
  late int port;

  // ── Principal (CX1) ───────────────────────────────────────────────────
  late PdvDatabase principalDatabase;
  late OfflineFirstGateway principalGateway;
  late ApiClient principalApi;
  late LocalTopologyService principal;

  // ── Nuvem de mentira ──────────────────────────────────────────────────
  //
  // Sem ela, este arquivo escondia o bug: com a nuvem inalcançável, a
  // reconciliação remota de `_readLocalFirst` falhava e a resposta LOCAL
  // (correta) prevalecia. Em produção a nuvem responde — e é ela que devolve
  // a sessão do terminal ERRADO. A nuvem falsa responde exatamente como o
  // backend: pelo `X-Terminal-Id` que chegou na requisição.
  late HttpServer fakeCloud;
  final cloudTerminalHeaders = <String>[];
  Map<String, dynamic>? cloudSessionForPrincipal;

  // Serviços-cliente abertos durante um teste, para fechar todos no tearDown
  // mesmo quando o teste cria mais de um secundário.
  final clients = <LocalTopologyService>[];

  Future<int> freePort() async {
    final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final p = socket.port;
    await socket.close();
    return p;
  }

  /// Sobe o Principal com um caixa (`CashStation`) já cadastrado para cada
  /// terminal que o teste for abrir, e o vincula à identidade PRÓPRIA do
  /// Principal (`cx1Operator`/`cx1Node`) — exatamente como `home_page.dart`
  /// vincula `gateway.installationId` e o escopo da sessão ao operador que
  /// está de fato na frente deste computador.
  Future<void> startPrincipal({
    required String cx1Operator,
    required String cx1Node,
  }) async {
    final sep = Platform.pathSeparator;
    principalDatabase = PdvDatabase(
      file: File('${temporaryDirectory.path}${sep}principal.sqlite'),
    );
    await principalDatabase.ready;
    principalGateway = OfflineFirstGateway(
      database: principalDatabase,
      queue: SyncQueueService(database: principalDatabase),
      fiscalQueue: FiscalQueueService(database: principalDatabase),
    );
    // A nuvem falsa responde `/cash-register/current/` de acordo com o
    // `X-Terminal-Id` recebido — é assim que o backend de verdade resolve a
    // sessão (`installation_id_from_request`). Guardar os cabeçalhos permite
    // afirmar DE QUEM o principal se identificou ao perguntar.
    fakeCloud = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    unawaited(
      fakeCloud.forEach((request) async {
        final terminal = request.headers.value('x-terminal-id') ?? '';
        await request.drain<void>();
        if (request.uri.path.endsWith('/cash-register/current/')) {
          cloudTerminalHeaders.add(terminal);
          final session = terminal == cx1Node ? cloudSessionForPrincipal : null;
          if (session != null) {
            request.response
              ..statusCode = HttpStatus.ok
              ..headers.contentType = ContentType.json
              ..write(jsonEncode(session));
          } else {
            request.response
              ..statusCode = HttpStatus.notFound
              ..headers.contentType = ContentType.json
              ..write(
                jsonEncode(const {
                  'detail': 'O operador não possui uma sessão de caixa em '
                      'andamento.',
                }),
              );
          }
          await request.response.close();
          return;
        }
        // Todo o RESTO continua como antes deste arquivo ganhar nuvem: fora
        // do ar. Assim os outros testes seguem exercitando exatamente o mesmo
        // caminho de sempre, e só `current/` passa a ter uma nuvem que
        // responde — que é onde vive o defeito.
        request.response
          ..statusCode = HttpStatus.serviceUnavailable
          ..headers.contentType = ContentType.json
          ..write(jsonEncode(const {'detail': 'nuvem fora do ar no teste'}));
        await request.response.close();
      }),
    );

    principalApi = ApiClient(
      baseUrl: 'http://127.0.0.1:${fakeCloud.port}/api/v1',
    );
    principalApi.attachLocalStore(gateway: principalGateway);
    // O mesmo token (formatado como JWT, com o payload batendo o escopo) tem
    // de ir tanto para o bind manual abaixo quanto para o `accessToken` do
    // `LocalTopologyService` do Principal: `_serveRead` chama `api.get(...,
    // accessToken: accessToken)` a cada leitura relayada, e isso RECALCULA o
    // escopo do gateway a partir do token (`ApiClient._rememberSession`). Um
    // token que não decodifique para o MESMO escopo reescreve `_scope` no
    // meio do teste, e os dados do CX1 — gravados sob o escopo antigo — somem
    // de baixo dos pés da leitura seguinte.
    final cx1Token = _fakeJwt(accountId: accountId, userId: cx1Operator);
    // O escopo TEM de sair da mesma authority do `baseUrl`: qualquer chamada
    // com token recalcula o escopo a partir dele (`_rememberSession`), e um
    // valor fixo aqui faria o gateway trocar de escopo no meio do teste —
    // levando junto tudo o que já estava gravado no escopo anterior.
    principalGateway.bindSession(
      scope: '127.0.0.1:${fakeCloud.port}|$accountId:$cx1Operator',
      restaurantId: restaurantId,
    );
    // A identidade do PRÓPRIO terminal: é o que o gateway usa quando NINGUÉM
    // está relayando por ele (`RelayOrigin.current == null`).
    principalGateway.installationId = cx1Node;
    await principalGateway.repository(EntityCatalog.cashStation).applyRemoteList([
      {
        'id': 'estacao-cx1',
        'name': 'Caixa 1',
        'restaurant': restaurantId,
        'operators': const [],
      },
      {
        'id': 'estacao-cx2',
        'name': 'Caixa 2',
        'restaurant': restaurantId,
        'operators': const [],
      },
    ]);
    await principalGateway.recordSync(EntityCatalog.cashStation);

    secret = LocalTopologyStore.generatePairingSecret();
    principal = LocalTopologyService(
      api: principalApi,
      accessToken: cx1Token,
      accountId: accountId,
      actorId: cx1Operator,
      restaurantId: restaurantId,
      store: LocalTopologyStore(
        file: File(
          '${temporaryDirectory.path}${Platform.pathSeparator}principal-topologia.sqlite',
        ),
        secretStorage: _MemorySecretStorage(),
      ),
    );
    for (var tentativa = 0; tentativa < 5; tentativa++) {
      port = await freePort();
      await principal.reconfigure(
        LocalTopologyConfig(
          mode: LocalTopologyMode.principal,
          nodeId: cx1Node,
          port: port,
          pairingSecret: secret,
          trustedNetworkAcknowledged: true,
        ),
      );
      if (principal.status.phase == LocalTopologyPhase.principalReady) break;
    }
    expect(principal.status.phase, LocalTopologyPhase.principalReady);
  }

  /// Abre um Secundário de verdade: outra instância de [LocalTopologyService],
  /// em modo cliente, com a SUA PRÓPRIA identidade (`actorId`/`nodeId`) — o
  /// par que decide de quem é a sessão de caixa no Principal.
  Future<LocalTopologyService> startClient({
    required String actorId,
    required String nodeId,
    String? name,
  }) async {
    final client = LocalTopologyService(
      api: ApiClient(baseUrl: 'http://127.0.0.1:9/api/v1'),
      accessToken: 'token-$actorId',
      accountId: accountId,
      actorId: actorId,
      restaurantId: restaurantId,
      store: LocalTopologyStore(
        file: File(
          '${temporaryDirectory.path}${Platform.pathSeparator}'
          '${name ?? actorId}-topologia.sqlite',
        ),
        secretStorage: _MemorySecretStorage(),
      ),
    );
    await client.reconfigure(
      LocalTopologyConfig(
        mode: LocalTopologyMode.client,
        nodeId: nodeId,
        principalHost: '127.0.0.1',
        port: port,
        pairingSecret: secret,
        trustedNetworkAcknowledged: true,
      ),
    );
    expect(await client.probe(), isTrue);
    clients.add(client);
    return client;
  }

  /// Abre a sessão do CX1 diretamente no gateway do Principal — a mesma
  /// chamada que a tela de caixa do próprio computador faria, sem passar pelo
  /// relay: é ele quem está na frente desta máquina.
  Future<Map<String, dynamic>> openCx1Session({
    String station = 'estacao-cx1',
    String amount = '100.00',
  }) async {
    final result = await principalGateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': station, 'opening_amount': amount},
      context: {
        'cash_station': {'id': station, 'name': 'Caixa 1'},
        'operator_name': 'Operador CX1',
      },
    );
    return result.payload;
  }

  /// Lê `/cash-register/current/` como o próprio Principal leria (sem relay).
  Future<Map<String, dynamic>> readCx1Current() =>
      principalGateway.read('/cash-register/current/', query: {'restaurant': restaurantId});

  /// `current/` pelo relay, normalizado: `null` para "sem sessão".
  ///
  /// Sem servidor de nuvem de verdade neste teste (o Principal fala com
  /// `127.0.0.1:9`, porta sempre fechada), o gateway devolve `_empty: true`
  /// localmente e AINDA tenta confirmar com a "nuvem" antes de responder —
  /// exatamente como faria com um servidor de verdade fora do ar. Essa
  /// tentativa falha aqui, e o resultado chega como `ApiException` 404 em vez
  /// do dicionário `_empty` limpo que um backend real devolveria. As duas
  /// formas significam a MESMA coisa ("nenhuma sessão"), e é isso que os
  /// testes deste arquivo precisam distinguir de verdade: nunca a sessão do
  /// terminal errado.
  Future<Map<String, dynamic>?> currentFor(LocalTopologyService client) async {
    try {
      final result = await client.read(
        const RelayRead(
          path: '/cash-register/current/',
          query: {'restaurant': restaurantId},
        ),
      );
      return result['_empty'] == true ? null : result;
    } on ApiException catch (error) {
      expect(error.statusCode, 404);
      return null;
    }
  }

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'starchef-relay-cash-identity-',
    );
  });

  tearDown(() async {
    for (final client in clients) {
      await client.shutdown();
    }
    clients.clear();
    await principal.shutdown();
    await principalApi.dispose();
    await principalDatabase.close();
    await fakeCloud.close(force: true);
    cloudTerminalHeaders.clear();
    cloudSessionForPrincipal = null;
    for (var attempt = 0; attempt < 5; attempt++) {
      try {
        if (await temporaryDirectory.exists()) {
          await temporaryDirectory.delete(recursive: true);
        }
        break;
      } on FileSystemException {
        await Future<void>.delayed(const Duration(milliseconds: 120));
      }
    }
  });

  group('CX2 lendo pela rede local nunca herda o caixa do CX1', () {
    setUp(() async {
      await startPrincipal(cx1Operator: 'operador-cx1', cx1Node: 'no-cx1');
    });

    test(
      'CX1 com caixa aberto — CX2 sem caixa próprio lê vazio, não o do CX1',
      () async {
        final aberta = await openCx1Session();
        final cx2 = await startClient(actorId: 'operador-cx2', nodeId: 'no-cx2');

        final resposta = await currentFor(cx2);

        // O bug devolvia exatamente `aberta` aqui — a sessão do CX1.
        expect(resposta, isNull);
        expect(aberta['id'], isNotNull);
      },
    );

    test(
      'CX2 abre o próprio caixa e lê O DELE, não o do CX1',
      () async {
        final doCx1 = await openCx1Session(station: 'estacao-cx1');
        final cx2 = await startClient(actorId: 'operador-cx2', nodeId: 'no-cx2');

        final aberturaCx2 = await cx2.relay(
          const RelayMutation(
            method: 'POST',
            path: '/cash-register/open/',
            operationId: 'cx2-abre-caixa-0001',
            body: {'cash_station': 'estacao-cx2', 'opening_amount': '50.00'},
          ),
        );
        expect(aberturaCx2['cash_station'], 'estacao-cx2');

        final leituraCx2 = await cx2.read(
          const RelayRead(
            path: '/cash-register/current/',
            query: {'restaurant': restaurantId},
          ),
        );

        expect(leituraCx2['id'], aberturaCx2['id']);
        expect(leituraCx2['cash_station'], 'estacao-cx2');
        expect(leituraCx2['id'], isNot(doCx1['id']));
      },
    );

    test(
      'depois que o CX2 abre o dele, o CX1 continua vendo só o próprio',
      () async {
        final doCx1 = await openCx1Session(station: 'estacao-cx1');
        final cx2 = await startClient(actorId: 'operador-cx2', nodeId: 'no-cx2');
        await cx2.relay(
          const RelayMutation(
            method: 'POST',
            path: '/cash-register/open/',
            operationId: 'cx2-abre-caixa-0002',
            body: {'cash_station': 'estacao-cx2', 'opening_amount': '50.00'},
          ),
        );

        final leituraCx1 = await readCx1Current();

        expect(leituraCx1['id'], doCx1['id']);
        expect(leituraCx1['cash_station'], 'estacao-cx1');
      },
    );

    test(
      'o mesmo operador em outra máquina não herda a sessão (regra 5, de ponta a ponta)',
      () async {
        // Reabre o Principal com o MESMO operador que o "secundário" abaixo
        // vai usar — é o caso mais traiçoeiro: a checagem por operador passa
        // sozinha, só a instalação separa uma gaveta da outra.
        await principal.shutdown();
        await startPrincipal(cx1Operator: 'gerente', cx1Node: 'no-cx1');
        final aberta = await openCx1Session();

        final mesmoOperadorOutraMaquina = await startClient(
          actorId: 'gerente',
          nodeId: 'no-cx2',
        );

        final resposta = await currentFor(mesmoOperadorOutraMaquina);

        expect(resposta, isNull);
        expect(aberta['id'], isNotNull);
      },
    );

    test(
      'dois secundários distintos nunca se enxergam um ao outro',
      () async {
        await openCx1Session();
        final cx2 = await startClient(actorId: 'operador-cx2', nodeId: 'no-cx2');
        final cx3 = await startClient(actorId: 'operador-cx3', nodeId: 'no-cx3');

        await cx2.relay(
          const RelayMutation(
            method: 'POST',
            path: '/cash-register/open/',
            operationId: 'cx2-abre-caixa-0003',
            body: {'cash_station': 'estacao-cx2', 'opening_amount': '30.00'},
          ),
        );

        final leituraCx3 = await currentFor(cx3);

        expect(leituraCx3, isNull);
      },
    );

    test(
      'com a nuvem ALCANÇÁVEL, o CX2 ainda não recebe a sessão do CX1',
      () async {
        // O caso de produção que os outros testes deste arquivo escondiam.
        //
        // Quando a leitura local do CX2 responde "sem sessão" (a correção da
        // v1.8.4 funcionando), `_readLocalFirst` NÃO devolve isso: ele trata
        // "não achei" como motivo para confirmar com o servidor. O principal
        // repete o mesmo raciocínio e pergunta à nuvem — só que se
        // identificando com o `X-Terminal-Id` DELE, porque a reconciliação não
        // leva a origem. A nuvem responde sobre o PRINCIPAL, e essa resposta
        // volta como se fosse a resposta para o CX2.
        //
        // Com a nuvem inalcançável (como estava neste arquivo antes), a
        // reconciliação falhava e a resposta local correta prevalecia — o bug
        // ficava invisível no teste e vivo em produção.
        final doCx1 = await openCx1Session();
        cloudSessionForPrincipal = {
          'id': '${doCx1['id']}',
          'restaurant': restaurantId,
          'cash_station': 'estacao-cx1',
          'cash_station_name': 'Caixa 1',
          'status': 'open',
          'station': 'PDV principal',
          'opening_amount': '100.00',
          'current_balance': '100.00',
          'opened_by': 'operador-cx1',
          'opened_terminal_installation_id': 'no-cx1',
          'movements': const <Map<String, dynamic>>[],
        };

        final cx2 = await startClient(actorId: 'operador-cx2', nodeId: 'no-cx2');
        final resposta = await currentFor(cx2);

        expect(
          resposta,
          isNull,
          reason: 'o CX2 recebeu a sessão do CX1 vinda da nuvem',
        );
        // E o motivo de raiz: se o principal foi à nuvem enquanto atendia o
        // CX2, ele não pode ter se identificado como ELE MESMO.
        expect(
          cloudTerminalHeaders,
          isNot(contains('no-cx1')),
          reason: 'o principal perguntou à nuvem com a identidade dele '
              'enquanto respondia pelo CX2',
        );
      },
    );

    test(
      'com caixa PRÓPRIO aberto, o CX2 não perde a sessão para a nuvem',
      () async {
        // O caminho IRMÃO do teste acima. Lá a leitura local do CX2 vinha
        // vazia e a nuvem era consultada na frente de quem esperava. Aqui a
        // leitura local ACERTA — o CX2 tem caixa dele — e `_readLocalFirst`
        // responde na hora; mas dispara `_refreshFromServer` por trás, sem
        // ninguém esperando, com a mesma identidade errada. A nuvem devolve a
        // sessão do PRINCIPAL, e `_storeRemote` a grava por cima da do CX2:
        // a tela abre certa e troca de caixa sozinha um instante depois.
        final doCx1 = await openCx1Session();
        cloudSessionForPrincipal = {
          'id': '${doCx1['id']}',
          'restaurant': restaurantId,
          'cash_station': 'estacao-cx1',
          'cash_station_name': 'Caixa 1',
          'status': 'open',
          'station': 'PDV principal',
          'opening_amount': '100.00',
          'current_balance': '100.00',
          'opened_by': 'operador-cx1',
          'opened_terminal_installation_id': 'no-cx1',
          'movements': const <Map<String, dynamic>>[],
        };

        final cx2 = await startClient(actorId: 'operador-cx2', nodeId: 'no-cx2');
        final aberturaCx2 = await cx2.relay(
          const RelayMutation(
            method: 'POST',
            path: '/cash-register/open/',
            operationId: 'cx2-abre-caixa-0009',
            body: {'cash_station': 'estacao-cx2', 'opening_amount': '50.00'},
          ),
        );

        final primeira = await currentFor(cx2);
        expect(primeira?['id'], aberturaCx2['id']);

        // Tempo de sobra para a reconciliação de fundo terminar — é
        // justamente por não ser esperada por ninguém que ela passaria
        // despercebida.
        await Future<void>.delayed(const Duration(milliseconds: 300));

        final segunda = await currentFor(cx2);
        expect(
          segunda?['id'],
          aberturaCx2['id'],
          reason: 'a sessão do CX1 sobrescreveu a do CX2 pela reconciliação '
              'de fundo',
        );
        expect(segunda?['cash_station'], 'estacao-cx2');
        expect(
          cloudTerminalHeaders,
          isNot(contains('no-cx1')),
          reason: 'o principal perguntou à nuvem com a identidade dele '
              'enquanto respondia pelo CX2',
        );
      },
    );

    test(
      'a mesma isolação vale pelo alias GET /local/, não só por POST /v1/read',
      () async {
        // `LocalTopologyService.read()` sempre fala por `/v1/read`; o alias
        // `/local/...` é um caminho HTTP separado (pensado para um cliente
        // mais simples), e o bug foi corrigido nos DOIS pontos de entrada —
        // este teste cobre o outro, com uma assinatura manual.
        final aberta = await openCx1Session();

        final response = await _signedLocalGet(
          port: port,
          secret: secret,
          accountId: accountId,
          restaurantId: restaurantId,
          actorId: 'operador-cx2',
          nodeId: 'no-cx2',
          path: '/local/cash-register/current',
        );

        // Sucesso (`_empty: true`) OU o 404 de "sem confirmação da nuvem"
        // (ver `currentFor`) — os dois significam "sem sessão para o CX2".
        // O bug devolvia 200 com a sessão do CX1 dentro de `result`.
        if (response.status == HttpStatus.ok) {
          expect(response.body['result']['_empty'], isTrue);
        } else {
          expect(response.status, HttpStatus.notFound);
        }
        expect(aberta['id'], isNotNull);
      },
    );
  });
}

/// Réplica mínima do `call()` de `local_api_server_test.dart`, para exercitar
/// o alias `GET /local/...` com uma identidade escolhida à mão — sem passar
/// pela abstração `LocalTopologyService.read()`, que só fala por `/v1/read`.
Future<({int status, Map<String, dynamic> body})> _signedLocalGet({
  required int port,
  required String secret,
  required String accountId,
  required String restaurantId,
  required String actorId,
  required String nodeId,
  required String path,
}) async {
  final timestamp = DateTime.now().toUtc().millisecondsSinceEpoch ~/ 1000;
  const nonce = 'nonce-teste-local-alias';
  final signature = LocalRelayAuthenticator.signature(
    secret: secret,
    method: 'GET',
    path: path,
    timestamp: timestamp,
    nonce: nonce,
    account: accountId,
    actor: actorId,
    restaurant: restaurantId,
    nodeId: nodeId,
    body: '',
  );
  final client = HttpClient();
  try {
    final request = await client.openUrl(
      'GET',
      Uri.parse('http://127.0.0.1:$port$path'),
    );
    request.headers
      ..set('x-starchef-timestamp', '$timestamp')
      ..set('x-starchef-nonce', nonce)
      ..set('x-starchef-node', nodeId)
      ..set('x-starchef-account', accountId)
      ..set('x-starchef-actor', actorId)
      ..set('x-starchef-restaurant', restaurantId)
      ..set('x-starchef-signature', signature);
    final response = await request.close();
    final raw = await utf8.decoder.bind(response).join();
    final decoded = raw.isEmpty ? const {} : jsonDecode(raw) as Map;
    return (
      status: response.statusCode,
      body: Map<String, dynamic>.from(decoded),
    );
  } finally {
    client.close(force: true);
  }
}

/// Um JWT de mentira — só a forma importa, ninguém confere assinatura aqui —
/// cujo payload decodifica para o MESMO par (conta, operador) que o teste
/// bind no gateway. Ver o comentário em `startPrincipal` sobre por que os
/// dois precisam bater.
String _fakeJwt({required String accountId, required String userId}) {
  final header = base64Url.encode(utf8.encode(jsonEncode({'alg': 'none'})));
  final payload = base64Url.encode(
    utf8.encode(jsonEncode({'account_id': accountId, 'user_id': userId})),
  );
  return '$header.$payload.assinatura-irrelevante-no-teste';
}

class _MemorySecretStorage implements TopologySecretStorage {
  String? _value;

  @override
  Future<String?> read() async => _value;

  @override
  Future<void> write(String value) async => _value = value;
}
