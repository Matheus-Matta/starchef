import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:starchef_pdv/core/data/cash_register_repository.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/local_id.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_operation.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/formatters/value_formatters.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/features/devices/domain/local_print_renderer.dart';

/// Teste FUNCIONAL: o núcleo real do PDV (SQLite, fila, gateway offline-first,
/// sincronização) falando com um backend Django DE VERDADE.
///
/// Mora fora de `test/` de propósito — precisa de servidor no ar e de dados
/// semeados; `flutter test` sem argumento não o encontra. Rode:
///
/// ```powershell
/// flutter test functional/ --dart-define=API_URL=http://127.0.0.1:8001/api/v1 `
///   --dart-define=USUARIO=admin --dart-define=SENHA=... `
///   --dart-define=SENHA_CAIXA=caixa123
/// ```
///
/// O que ele prova, na ordem em que o balcão vive:
/// 1. abrir caixa e sincronizar (id temporário vira real);
/// 2. abrir comanda, lançar o primeiro item (create-with-item) e o segundo
///    (/items/), sincronizar e reler do servidor: nada duplicado, nenhum
///    `offline-…` sobrando;
/// 3. receber em PIX e em dinheiro: a sessão (local e servidor) lista as
///    vendas por forma; a comanda volta ao salão;
/// 4. cancelar outra comanda só com a senha de ações do caixa;
/// 5. fechar o caixa e montar o relatório impresso com as vendas por forma.
void main() {
  const apiUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://127.0.0.1:8001/api/v1',
  );
  const usuario = String.fromEnvironment('USUARIO', defaultValue: 'admin');
  const senha = String.fromEnvironment('SENHA');
  const senhaCaixa = String.fromEnvironment(
    'SENHA_CAIXA',
    defaultValue: 'caixa123',
  );

  late Directory directory;
  late PdvDatabase database;
  late OfflineFirstGateway gateway;
  late ApiClient api;
  late SyncService sync;
  late String token;
  late String restaurantId;
  final installationId = 'functional-${LocalId.uuid()}';

  Map<String, dynamic> terminalIdentity() => {
    'terminal_installation_id': installationId,
    'terminal_name': 'Teste funcional',
    'terminal_type': 'desktop',
    'terminal_role': 'principal',
    'device_identifier': installationId,
  };

  /// Sobe a fila e espera esvaziar.
  ///
  /// `push()` divide a fila com o flush do `ApiClient` (debounce de 450 ms):
  /// uma operação que ele já reservou não é reenviada aqui, e `push()` volta
  /// antes de ela terminar. O que o teste quer é "o servidor já sabe".
  Future<void> sincronizar() async {
    await sync.push();
    final deadline = DateTime.now().add(const Duration(seconds: 10));
    while (DateTime.now().isBefore(deadline)) {
      final entries = await gateway.queue.entries(scope: gateway.scope!);
      final open = entries.where((e) => e.status != SyncQueueStatus.synced);
      if (open.isEmpty) return;
      if (open.any((e) => e.status == SyncQueueStatus.failed)) {
        fail(
          'Operação recusada pelo servidor: ${open.map((e) => '${e.path} ${e.lastError} body=${e.payload}').join('; ')}',
        );
      }
      await Future<void>.delayed(const Duration(milliseconds: 150));
      await sync.push();
    }
    fail('A fila não esvaziou em 10 s.');
  }

  /// Leitura DIRETA do servidor, sem passar pelo SQLite local.
  Future<Map<String, dynamic>> servidor(String path) =>
      api.syncTransport.send('GET', path);

  Future<List<Map<String, dynamic>>> lista(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final page = await api.get(path, query: query, accessToken: token);
    return (page['results'] as List).cast<Map<String, dynamic>>();
  }

  setUpAll(() async {
    expect(senha, isNotEmpty, reason: 'passe --dart-define=SENHA=...');
    directory = await Directory.systemTemp.createTemp('starchef-funcional');
    final sep = Platform.pathSeparator;
    database = PdvDatabase(file: File('${directory.path}${sep}pdv.sqlite'));
    await database.ready;
    final queue = SyncQueueService(database: database);
    gateway = OfflineFirstGateway(
      database: database,
      queue: queue,
      fiscalQueue: FiscalQueueService(database: database),
    );
    api = ApiClient(
      baseUrl: apiUrl,
      client: http.Client(),
      offlineStore: OfflineStore(
        file: File('${directory.path}${sep}legacy.sqlite'),
      ),
    );
    sync = SyncService(gateway: gateway, transport: api.syncTransport);
    api.attachLocalStore(gateway: gateway, syncService: sync);

    final login = await api.post(
      '/auth/login/',
      body: {'username': usuario, 'password': senha, 'no_cookie': true},
    );
    token = '${login['access']}';
    restaurantId = '${(login['user'] as Map)['restaurant_id']}';
    // A primeira chamada autenticada vincula o escopo do banco local; o
    // restaurante e a identidade do terminal são o que a tela também fixa.
    await api.get('/auth/me/', accessToken: token);
    gateway
      ..bindSession(scope: api.sessionScope!, restaurantId: restaurantId)
      ..installationId = installationId;
    // Carga inicial: cardápio, comandas, caixas, formas de pagamento.
    await sync.pullAll(restaurantId: restaurantId, force: true);
    // Uma sessão que sobrou de uma rodada interrompida pertence a OUTRO
    // terminal (a instalação muda a cada execução) e bloquearia a abertura.
    try {
      final leftover = await servidor('/cash-register/current/');
      if ('${leftover['id'] ?? ''}'.isNotEmpty) {
        fail(
          'Já existe um caixa aberto para $usuario '
          '(${leftover['terminal_label']}). Feche-o ou cancele-o antes de '
          'rodar: python backend/manage.py shell -c "..."',
        );
      }
    } on ApiException catch (error) {
      // 404 = nenhum caixa aberto: é o estado esperado. 403/409 = sessão de
      // outra instalação (rodada anterior interrompida).
      if (error.statusCode != 404) {
        fail(
          'Caixa preso de uma rodada anterior: ${error.message} '
          'Cancele a sessão no backend antes de rodar.',
        );
      }
    }
  });

  tearDownAll(() async {
    await sync.dispose();
    await api.dispose();
    // Um flush do `ApiClient` disparado pelo último `post` (debounce de
    // 450 ms) ainda pode estar tocando o banco; fechar antes dele terminar
    // vira "connection pool is closed" no meio do teardown.
    await Future<void>.delayed(const Duration(seconds: 1));
    await database.close();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  late String sessionId;
  late Map<String, dynamic> product;
  late Map<String, dynamic> cashMethod;
  late Map<String, dynamic> pixMethod;
  late List<Map<String, dynamic>> commands;

  test('1. caixa abre local e ganha id real ao sincronizar', () async {
    final stations = await lista(
      '/cash-stations/',
      query: {'restaurant': restaurantId, 'page_size': 50},
    );
    // Superusuário enxerga os caixas de todos os restaurantes: o caixa tem
    // de ser DESTE restaurante, senão o recebimento do pedido é recusado
    // ("sessão não está mais aberta para este operador").
    final userId = '${gateway.operatorId}';
    final station = stations.firstWhere(
      (item) =>
          '${item['restaurant']}' == restaurantId &&
          (item['operators'] as List? ?? const [])
              .map((id) => '$id')
              .contains(userId),
      orElse: () => throw StateError(
        'Semeie um caixa do restaurante $restaurantId com o operador $userId.',
      ),
    );
    final opened = await api.post(
      '/cash-register/open/',
      body: {
        'cash_station': station['id'],
        'opening_amount': '150.00',
        'notes': 'Teste funcional',
        ...terminalIdentity(),
      },
      accessToken: token,
      localContext: {'cash_station': station, 'operator_name': usuario},
    );
    expect('${opened['id']}', startsWith('offline-'));

    await sincronizar();

    var current = await servidor('/cash-register/current/');
    sessionId = '${current['id']}';
    expect(sessionId, isNot(startsWith('offline-')));
    // Conferência cega: o troco inicial precisa bater com o contado do último
    // fechamento deste caixa; se não bater, a sessão nasce aguardando
    // aprovação e nenhum recebimento entra nela. Aqui vale a mesma saída da
    // tela: aprovar a divergência com a senha de ações do caixa.
    if ('${current['status']}' == 'pending_manager_approval') {
      await api.syncTransport.send(
        'POST',
        '/cash-register/$sessionId/approve/',
        body: {'reason': 'Teste funcional', 'cash_password': senhaCaixa},
      );
      current = await servidor('/cash-register/current/');
    }
    expect(current['status'], 'open');
    expect(ValueFormatters.number(current['opening_amount']), 150.0);
    // O local já conhece a sessão pelo id real.
    final local = await api.get('/cash-register/current/', accessToken: token);
    expect('${local['id']}', sessionId);
  });

  test(
    '2. comanda: primeiro e segundo item sincronizam sem duplicar',
    () async {
      final products = await lista(
        '/menu/products/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 200,
        },
      );
      product = products.firstWhere(
        (item) => '${item['pricing_unit'] ?? 'unit'}' != 'kg',
      );
      commands = await lista(
        '/commands/',
        query: {'restaurant': restaurantId, 'status': 'free', 'page_size': 50},
      );
      expect(commands.length, greaterThanOrEqualTo(5));
      final command = commands[0];

      final draft = await api.post(
        '/orders/open-command/',
        body: {'command': command['id']},
        accessToken: token,
        localContext: {'command': command},
      );
      final localOrderId = '${draft['id']}';
      expect(localOrderId, startsWith('offline-'));

      await api.post(
        '/orders/$localOrderId/items/',
        body: {'product': product['id'], 'quantity': 1},
        accessToken: token,
      );
      await api.post(
        '/orders/$localOrderId/items/',
        body: {
          'product': product['id'],
          'quantity': 2,
          'customer_note': 'sem cebola',
        },
        accessToken: token,
      );
      await sincronizar();

      // O id temporário resolve para o real em todo lugar.
      final local = await api.get('/orders/$localOrderId/', accessToken: token);
      final realOrderId = '${local['id']}';
      expect(realOrderId, isNot(startsWith('offline-')));
      final remote = await servidor('/orders/$realOrderId/');
      final remoteItems = (remote['items'] as List).cast<Map>();
      expect(remoteItems, hasLength(2));

      // Reconciliação: a leitura do servidor NÃO soma o item de novo, e nenhum
      // `offline-…` sobra na cópia local.
      await gateway.orders.applyRemote(remote);
      final reconciled = await api.get(
        '/orders/$realOrderId/',
        accessToken: token,
      );
      final localItems = (reconciled['items'] as List).cast<Map>();
      expect(localItems, hasLength(2));
      expect(
        localItems.map((item) => '${item['id']}'),
        everyElement(isNot(startsWith('offline-'))),
      );
      expect(
        ValueFormatters.number(reconciled['total']),
        ValueFormatters.number(remote['total']),
      );
      commands[0]['_order'] = realOrderId;
    },
  );

  test(
    '3. PIX + dinheiro: vendas por forma na sessão; comanda liberada',
    () async {
      final methods = await lista(
        '/payments/methods/',
        query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 50},
      );
      cashMethod = methods.firstWhere((m) => m['method_type'] == 'cash');
      pixMethod = methods.firstWhere((m) => m['method_type'] == 'pix');
      final orderId = '${commands[0]['_order']}';
      await api.post(
        '/orders/$orderId/close/',
        body: {'discount': 0, 'service_fee_enabled': false},
        accessToken: token,
      );
      final closed = await api.get('/orders/$orderId/', accessToken: token);
      final total = ValueFormatters.number(closed['total']);
      final half = (total / 2).toStringAsFixed(2);
      final rest = (total - double.parse(half)).toStringAsFixed(2);

      await api.post(
        '/orders/$orderId/pay/',
        body: {
          'payment_method': pixMethod['id'],
          'amount': half,
          'cash_register': sessionId,
        },
        accessToken: token,
        localContext: {'payment_method': pixMethod},
      );
      await api.post(
        '/orders/$orderId/pay/',
        body: {
          'payment_method': cashMethod['id'],
          'amount': rest,
          'cash_register': sessionId,
        },
        accessToken: token,
        localContext: {'payment_method': cashMethod},
      );
      // Antes de subir: a cópia LOCAL já lista as duas formas e a gaveta só
      // conta o dinheiro. Leitura direta do SQLite: com rede, `api.get` de
      // `/cash-register/current/` prefere o servidor, que ainda não sabe.
      var local = await gateway.read('/cash-register/current/');
      expect(
        CashRegisterRepository.salesOf(local).map((s) => s['method_type']),
        containsAll(['pix', 'cash']),
      );
      expect(
        ValueFormatters.number(local['current_balance']),
        closeTo(150 + double.parse(rest), 0.001),
      );

      await sincronizar();

      final remote = await servidor('/cash-register/$sessionId/');
      final remoteSales = (remote['sales'] as List).cast<Map>();
      expect(
        remoteSales.map((s) => s['method_type']),
        containsAll(['pix', 'cash']),
      );
      expect(remoteSales.map((s) => s['order']), everyElement(orderId));
      // A cópia do servidor substitui a local sem contar duas vezes.
      await gateway.cashRegister.applyRemote(remote);
      local = await gateway.read('/cash-register/current/');
      expect(CashRegisterRepository.salesOf(local), hasLength(2));

      // A comanda voltou ao salão nos dois lados.
      final paid = await servidor('/orders/$orderId/');
      expect(paid['status'], 'paid');
      final commandRemote = await servidor('/commands/${commands[0]['id']}/');
      expect(commandRemote['status'], 'free');
      await gateway
          .repository(EntityCatalog.command)
          .applyRemote(commandRemote);
      final commandLocal = await api.get(
        '/commands/${commands[0]['id']}/',
        accessToken: token,
      );
      expect(commandLocal['status'], 'free');
      expect(commandLocal['current_order_id'], isNull);
    },
  );

  test('4. cancelar pedido só com a senha de ações do caixa', () async {
    final command = commands[1];
    final draft = await api.post(
      '/orders/open-command/',
      body: {'command': command['id']},
      accessToken: token,
      localContext: {'command': command},
    );
    await api.post(
      '/orders/${draft['id']}/items/',
      body: {'product': product['id'], 'quantity': 1},
      accessToken: token,
    );
    await sincronizar();
    final local = await api.get('/orders/${draft['id']}/', accessToken: token);
    final orderId = '${local['id']}';
    expect(orderId, isNot(startsWith('offline-')));

    // Senha errada é recusada; nenhum usuário é pedido.
    await expectLater(
      api.post(
        '/orders/$orderId/cancel/',
        body: {'reason': 'teste', 'cash_password': 'errada'},
        accessToken: token,
      ),
      throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 403)),
    );
    final cancelled = await api.post(
      '/orders/$orderId/cancel/',
      body: {'reason': 'Teste funcional', 'cash_password': senhaCaixa},
      accessToken: token,
    );
    expect(cancelled['status'], 'cancelled');
    final commandRemote = await servidor('/commands/${command['id']}/');
    expect(commandRemote['status'], 'free');
  });

  test(
    '4b. carência cancela sem senha; limite de comandas por mesa barra',
    () async {
      // Configuração do restaurante (form de Restaurantes > Operação).
      await api.syncTransport.send(
        'PATCH',
        '/restaurants/$restaurantId/',
        body: {'cancellation_grace_seconds': 120, 'max_commands_per_table': 1},
      );
      final command = commands[2];
      final draft = await api.post(
        '/orders/open-command/',
        body: {'command': command['id']},
        accessToken: token,
        localContext: {'command': command},
      );
      await api.post(
        '/orders/${draft['id']}/items/',
        body: {'product': product['id'], 'quantity': 1},
        accessToken: token,
      );
      await sincronizar();
      final local = await api.get(
        '/orders/${draft['id']}/',
        accessToken: token,
      );
      final orderId = '${local['id']}';
      // Enviado à cozinha dentro da carência: a rodada fica agendada.
      await api.syncTransport.send(
        'POST',
        '/orders/$orderId/send-to-kitchen/',
        body: {},
      );
      final sent = await servidor('/orders/$orderId/');
      expect((sent['items'] as List).first['status'], 'queued');

      // Sem senha: dentro da carência o servidor cancela direto.
      final cancelled = await api.post(
        '/orders/$orderId/cancel/',
        body: {'reason': 'Cliente desistiu'},
        accessToken: token,
      );
      expect(cancelled['status'], 'cancelled');
      expect(cancelled['cancel_authorization'], 'grace');

      // Limite de comandas por mesa = 1: a segunda comanda não senta.
      final tables = await lista(
        '/tables/',
        query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 50},
      );
      expect(tables, isNotEmpty);
      final table = tables.firstWhere(
        (t) => (t['active_commands'] as List? ?? const []).isEmpty,
      );
      final first = commands[3];
      final second = commands[4];
      await api.syncTransport.send(
        'POST',
        '/commands/${first['id']}/link-table/',
        body: {'table_id': table['id']},
      );
      await expectLater(
        api.syncTransport.send(
          'POST',
          '/commands/${second['id']}/link-table/',
          body: {'table_id': table['id']},
        ),
        throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 409)),
      );
      // Devolve a configuração e a mesa.
      await api.syncTransport.send(
        'POST',
        '/commands/${first['id']}/unlink-table/',
        body: {},
      );
      await api.syncTransport.send(
        'PATCH',
        '/restaurants/$restaurantId/',
        body: {'cancellation_grace_seconds': 0, 'max_commands_per_table': 4},
      );
    },
  );

  test(
    '5. fechamento: relatório impresso com gaveta e vendas por forma',
    () async {
      final before = await servidor('/cash-register/$sessionId/');
      final expected = '${before['current_balance']}';
      final closed = await api.post(
        '/cash-register/$sessionId/close/',
        body: {
          'actual_amount': expected,
          'notes': 'Fim do teste',
          ...terminalIdentity(),
        },
        accessToken: token,
      );
      await sincronizar();
      final remote = await servidor('/cash-register/$sessionId/');
      expect(remote['status'], 'closed');
      expect(ValueFormatters.number(remote['difference_amount']), 0);

      // O relatório é montado com o que o terminal tem na hora do fechamento.
      final text = CashPrintRenderer.closing(
        session: {
          ...closed,
          'sales': remote['sales'],
          'movements': remote['movements'],
        },
        restaurant: {'trade_name': 'Teste'},
        operatorName: usuario,
      );
      expect(text, contains('RELATORIO DE FECHAMENTO DE CAIXA'));
      expect(text, contains('(+) Abertura (troco)'));
      expect(text, contains('PIX'));
      expect(text, contains('Dinheiro'));
      expect(text, contains('Status: FECHADO'));
      String amount(String label) => text
          .split('\n')
          .firstWhere((line) => line.startsWith(label))
          .trimRight();
      expect(amount('(=) Esperado em caixa'), endsWith('R\$ $expected'));
      expect(amount('Diferenca'), endsWith('R\$ 0.00'));
      // Nada ficou na fila.
      final pending = await gateway.queue.entries(scope: gateway.scope!);
      expect(pending.where((e) => e.status != SyncQueueStatus.synced), isEmpty);
      stdout.writeln('\n$text');
    },
  );
}
