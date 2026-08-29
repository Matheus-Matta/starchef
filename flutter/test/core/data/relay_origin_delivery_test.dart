import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/relay_origin.dart';

import 'pdv_test_support.dart';

/// A fila do Caixa Principal entrega no nome de quem originou a operação.
///
/// O desenho da loja tem um caminho só até a nuvem: PDV 1 e PDV 2 escrevem no
/// SQLite do principal, e é o principal que sobe. Se ele subisse tudo com as
/// credenciais dele, a venda do PDV 2 chegaria ao backend no nome do PDV 1 —
/// e a sessão de caixa, que pertence ao par (operador, terminal), ficaria com
/// o dono errado. Por isso o secundário manda as credenciais dele junto, e
/// elas ficam gravadas com a operação.
void main() {
  late TestPdvStack stack;
  late FakeSyncTransport transport;
  late SyncService sync;

  const pdv2 = RelayOrigin(
    accessToken: 'token-do-pdv-2',
    refreshToken: 'refresh-do-pdv-2',
    actorId: 'operador-2',
    actorName: 'Maria',
    installationId: 'instalacao-do-pdv-2',
    terminalName: 'Balcão 02',
  );

  setUp(() async {
    stack = await TestPdvStack.create();
    stack.gateway.installationId = 'instalacao-do-principal';
    stack.gateway.terminalLabel = 'Caixa Principal';
    transport = FakeSyncTransport();
    sync = SyncService(gateway: stack.gateway, transport: transport);
  });

  tearDown(() async {
    sync.dispose();
    await stack.dispose();
  });

  Future<Map<String, dynamic>> abrirComoPdv2() async {
    final result = await RelayOrigin.runAs(
      pdv2,
      () => stack.gateway.write(
        'POST',
        '/cash-register/open/',
        body: {'cash_station': 'caixa-1', 'opening_amount': '100.00'},
        context: {
          'cash_station': {'id': 'caixa-1', 'name': 'Caixa Principal'},
          'operator_name': 'João (principal)',
        },
      ),
    );
    return result.payload;
  }

  test('a sessão nasce com o operador e o terminal de quem originou', () async {
    final session = await abrirComoPdv2();

    expect(session['opened_by'], 'operador-2');
    expect(session['opened_by_name'], 'Maria');
    expect(session['opened_terminal_installation_id'], 'instalacao-do-pdv-2');
    expect(session['opened_terminal_label'], 'Balcão 02');
  });

  test('a operação fica na fila com as credenciais do PDV 2', () async {
    await abrirComoPdv2();

    final entry = await stack.gateway.queue.claimNext(
      scope: TestPdvStack.scope,
    );

    expect(entry, isNotNull);
    expect(entry!.origin?.accessToken, 'token-do-pdv-2');
    expect(entry.origin?.actorId, 'operador-2');
    expect(entry.origin?.installationId, 'instalacao-do-pdv-2');
  });

  test('a entrega usa o token do PDV 2, não o do principal', () async {
    await abrirComoPdv2();

    await sync.push();

    final sent = transport.requests.singleWhere(
      (request) => request.path == '/cash-register/open/',
    );
    expect(sent.origin?.accessToken, 'token-do-pdv-2');
    expect(sent.origin?.installationId, 'instalacao-do-pdv-2');
  });

  test('uma operação do próprio principal sobe sem origem', () async {
    // Fora da zona de relay: é uma venda deste terminal, e ela usa a sessão
    // local — nenhuma indireção.
    await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-9', 'opening_amount': '50.00'},
      context: {
        'cash_station': {'id': 'caixa-9', 'name': 'Caixa 9'},
        'operator_name': 'João',
      },
    );

    await sync.push();

    final sent = transport.requests.singleWhere(
      (request) => request.path == '/cash-register/open/',
    );
    expect(sent.origin, isNull);
  });

  test('as duas origens convivem na mesma fila', () async {
    await abrirComoPdv2();
    await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-9', 'opening_amount': '50.00'},
      context: {
        'cash_station': {'id': 'caixa-9', 'name': 'Caixa 9'},
        'operator_name': 'João',
      },
    );

    await sync.push();

    final origins = transport.requests
        .where((request) => request.path == '/cash-register/open/')
        .map((request) => request.origin?.actorId)
        .toList();
    expect(origins, containsAll(<String?>['operador-2', null]));
  });

  test('a zona não vaza para a operação seguinte', () async {
    // O principal atende as próprias vendas e as dos secundários no mesmo
    // isolate. Um campo compartilhado seria lido pela operação errada no
    // primeiro `await` que as intercalasse; a zona acompanha a cadeia de
    // chamadas.
    final concorrente = stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {'cash_station': 'caixa-9', 'opening_amount': '50.00'},
      context: {
        'cash_station': {'id': 'caixa-9', 'name': 'Caixa 9'},
        'operator_name': 'João',
      },
    );
    final relayada = abrirComoPdv2();
    await Future.wait([concorrente, relayada]);

    final entries = <String?>[];
    for (var index = 0; index < 2; index++) {
      final entry = await stack.gateway.queue.claimNext(
        scope: TestPdvStack.scope,
      );
      entries.add(entry?.origin?.actorId);
      if (entry != null) await stack.gateway.queue.markSynced(entry.id);
    }

    expect(entries, containsAll(<String?>['operador-2', null]));
  });

  test('o token renovado fica gravado para a próxima tentativa', () async {
    await abrirComoPdv2();
    final entry = await stack.gateway.queue.claimNext(
      scope: TestPdvStack.scope,
    );

    await stack.gateway.queue.updateOrigin(
      entry!.id,
      pdv2.withTokens(access: 'token-renovado'),
    );

    final rows = await stack.database.query(
      'SELECT origin_json FROM sync_queue WHERE id = ?',
      [entry.id],
    );
    expect('${rows.single['origin_json']}', contains('token-renovado'));
    // O refresh continua lá: ele é o que permite renovar de novo depois.
    expect('${rows.single['origin_json']}', contains('refresh-do-pdv-2'));
  });

  test('a sessão do PDV 2 não aparece como sendo do principal', () async {
    await abrirComoPdv2();

    // O principal lê o próprio caixa: a sessão do PDV 2 não é dele.
    final atual = await stack.gateway.read('/cash-register/current/');
    expect(atual['_empty'], isTrue);

    // Já para o PDV 2, é a sessão dele.
    final doPdv2 = await RelayOrigin.runAs(
      pdv2,
      () => stack.gateway.read('/cash-register/current/'),
    );
    expect(doPdv2['opened_by'], 'operador-2');
  });

  test('o caixa continua único, venha de onde vier', () async {
    await abrirComoPdv2();

    // O principal tentando abrir o MESMO caixa: a exclusividade não olha de
    // quem é a operação, olha o caixa.
    await expectLater(
      stack.gateway.write(
        'POST',
        '/cash-register/open/',
        body: {'cash_station': 'caixa-1', 'opening_amount': '100.00'},
        context: {
          'cash_station': {'id': 'caixa-1', 'name': 'Caixa Principal'},
        },
      ),
      throwsA(isA<Exception>()),
    );

    final page = await stack.gateway
        .repository(EntityCatalog.cashSession)
        .list(query: const {'page_size': 50});
    expect(page.results, hasLength(1));
  });
}
