import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/cash_register_repository.dart';
import 'package:starchef_pdv/core/data/cash_session_status.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';

import 'pdv_test_support.dart';

/// O Caixa Principal como autoridade da sessão — inclusive sem internet.
///
/// Com a nuvem fora, é este SQLite que precisa dizer "este caixa já está
/// aberto". Se a exclusividade só existisse no servidor, ela valeria
/// justamente quando menos importa: com rede, o operador nem tentaria abrir
/// duas vezes.
void main() {
  late TestPdvStack stack;

  const balcao01 = 'no-de-instalacao-01';
  const balcao02 = 'no-de-instalacao-02';

  setUp(() async {
    stack = await TestPdvStack.create();
    // Sem servidor em nenhum destes testes: é o cenário que interessa.
    stack.gateway.connectivity = () => false;
    stack.gateway.installationId = balcao01;
    stack.gateway.terminalLabel = 'Balcão 01';
  });

  tearDown(() => stack.dispose());

  Future<Map<String, dynamic>> abrir({
    String station = 'caixa-1',
    String terminal = balcao01,
    String nome = 'Balcão 01',
  }) async {
    final result = await stack.gateway.write(
      'POST',
      '/cash-register/open/',
      body: {
        'cash_station': station,
        'opening_amount': '100.00',
        'terminal_installation_id': terminal,
        'terminal_name': nome,
      },
      context: {
        'cash_station': {'id': station, 'name': 'Caixa Principal'},
        'operator_name': 'João',
      },
    );
    return result.payload;
  }

  test('o operador é dono da sessão e do terminal onde abriu', () async {
    final session = await abrir();

    expect(session['status'], CashSessionStatus.open);
    expect(session['opened_by'], 'operador-1');
    expect(session['opened_terminal_installation_id'], balcao01);
    expect(session['opened_terminal_label'], 'Balcão 01');
  });

  test('o mesmo caixa não abre duas vezes, mesmo sem servidor', () async {
    await abrir();

    await expectLater(
      abrir(terminal: balcao02, nome: 'Balcão 02'),
      throwsA(
        isA<CashSessionConflict>().having(
          (error) => error.message,
          'mensagem',
          allOf(
            contains('Caixa Principal'),
            contains('transferência gerencial'),
          ),
        ),
      ),
    );

    // Nada meio-gravado: a recusa acontece na mesma transação da escrita.
    final page = await stack.gateway
        .repository(EntityCatalog.cashSession)
        .list(query: const {'page_size': 50});
    expect(page.results, hasLength(1));
  });

  test('um conflito não deixa operação órfã na fila', () async {
    await abrir();
    final antes = await stack.queue.entries(scope: TestPdvStack.scope);

    await expectLater(abrir(terminal: balcao02), throwsA(isA<ApiException>()));

    final depois = await stack.queue.entries(scope: TestPdvStack.scope);
    expect(depois.length, antes.length);
  });

  test('outro caixa cadastrado continua livre', () async {
    await abrir(station: 'caixa-1');

    final segunda = await abrir(station: 'caixa-2');

    expect(segunda['cash_station'], 'caixa-2');
  });

  test('o mesmo terminal recupera a sessão depois de reiniciar', () async {
    final aberta = await abrir();

    // Reiniciar o terminal não muda nem o operador nem a instalação.
    final atual = await stack.gateway.read('/cash-register/current/');

    expect(atual['id'], aberta['id']);
    expect(atual['_empty'], isNull);
  });

  test('a sessão não aparece para o mesmo operador em outra máquina', () async {
    await abrir();

    stack.gateway.installationId = balcao02;
    final atual = await stack.gateway.read('/cash-register/current/');

    expect(atual['_empty'], isTrue);
  });

  /// A sessão vinda do SERVIDOR também tem dona de máquina.
  ///
  /// O Caixa Secundário sincroniza as sessões da loja inteira — inclusive a do
  /// Principal. Enquanto o payload do servidor não trazia a instalação de quem
  /// abriu, `_belongsTo` não tinha com o que comparar e adotava a primeira
  /// sessão em aberto: o secundário mostrava o caixa do principal.
  Future<void> sincronizarDoServidor({
    required String id,
    required String operador,
    required String instalacao,
    String station = 'caixa-1',
  }) => stack.gateway
      .repository(EntityCatalog.cashSession)
      .applyRemoteList([
        {
          'id': id,
          'restaurant': 'rest-1',
          'cash_station': station,
          'cash_station_name': 'Caixa PDV 1',
          'status': CashSessionStatus.open,
          'opening_amount': '100.00',
          'current_balance': '100.00',
          'opened_by': operador,
          'opened_by_name': 'Operador',
          'opened_terminal_installation_id': instalacao,
          'opened_terminal_label': 'PDV 1',
          'movements': const [],
        },
      ]);

  test('o secundário não adota o caixa aberto no principal', () async {
    // A sessão do PDV 1, de outro operador, chegou pela sincronização.
    await sincronizarDoServidor(
      id: 'sessao-do-principal',
      operador: 'operador-2',
      instalacao: balcao02,
    );

    final atual = await stack.gateway.read('/cash-register/current/');

    expect(atual['_empty'], isTrue);
  });

  test('o mesmo operador em duas máquinas não herda a gaveta da outra', () async {
    // O caso que mais engana: é a MESMA pessoa, então a checagem por operador
    // passa. Só a instalação separa uma gaveta da outra.
    await sincronizarDoServidor(
      id: 'sessao-do-principal',
      operador: 'operador-1',
      instalacao: balcao02,
    );

    final atual = await stack.gateway.read('/cash-register/current/');

    expect(atual['_empty'], isTrue);
  });

  test('terminal que ainda não sabe a própria instalação não adota nada', () async {
    await sincronizarDoServidor(
      id: 'sessao-do-principal',
      operador: 'operador-1',
      instalacao: balcao02,
    );
    stack.gateway.installationId = null;

    final atual = await stack.gateway.read('/cash-register/current/');

    // Como no servidor: sessão com dona de máquina e cliente sem identidade é
    // tratada como outra máquina. Afrouxar aqui deixaria a regra contornável.
    expect(atual['_empty'], isTrue);
  });

  test('sessão antiga, sem máquina registrada, ainda é do seu operador', () async {
    await sincronizarDoServidor(
      id: 'sessao-antiga',
      operador: 'operador-1',
      instalacao: '',
    );

    final atual = await stack.gateway.read('/cash-register/current/');

    expect(atual['id'], 'sessao-antiga');
  });

  test('a sessão deste terminal sobrevive à sincronização', () async {
    final aberta = await abrir();
    // O servidor devolve a MESMA sessão, agora com a instalação no payload.
    await sincronizarDoServidor(
      id: '${aberta['id']}',
      operador: 'operador-1',
      instalacao: balcao01,
    );

    final atual = await stack.gateway.read('/cash-register/current/');

    expect(atual['id'], aberta['id']);
  });

  group('o nome do caixa que a tela mostra', () {
    test('é o nome REAL da estação, não o rótulo herdado', () async {
      final aberta = await abrir();

      // O campo `station` é texto livre herdado cujo padrão, no model do
      // backend e no payload local, é a string "PDV principal" — ninguém
      // nunca o preenche, porque nenhum cliente envia `station` ao abrir o
      // caixa. Lê-lo na tela fazia QUALQUER terminal exibir "PDV principal"
      // no lugar do caixa de verdade: num Caixa Secundário isso se parecia
      // exatamente com "estou vendo o caixa do Principal".
      expect(
        CashRegisterRepository.stationLabelOf(aberta),
        'Caixa Principal',
      );
    });

    test('cai para o rótulo herdado só quando não há nome de estação', () {
      expect(
        CashRegisterRepository.stationLabelOf(const {
          'station': 'Balcão da padaria',
        }),
        'Balcão da padaria',
      );
      expect(
        CashRegisterRepository.stationLabelOf(
          const {},
          fallback: 'Estação atual',
        ),
        'Estação atual',
      );
      // Nome vazio não conta como nome.
      expect(
        CashRegisterRepository.stationLabelOf(const {
          'cash_station_name': '   ',
          'station': 'Caixa 2',
        }),
        'Caixa 2',
      );
    });

    test('o literal herdado nunca é exibido como se fosse um caixa', () {
      // "PDV principal" é o padrão do model no backend — não descreve terminal
      // nenhum. Exibi-lo num Caixa Secundário se parece exatamente com "estou
      // vendo o caixa do Principal", que é o defeito relatado pela loja.
      expect(
        CashRegisterRepository.stationLabelOf(const {
          'station': 'PDV principal',
          'opened_terminal_label': 'Balcão 02',
        }),
        'Balcão 02',
      );
      // Sem nada melhor, um rótulo genérico — mas nunca o literal enganoso.
      expect(
        CashRegisterRepository.stationLabelOf(const {
          'station': 'PDV principal',
        }, fallback: 'Caixa'),
        'Caixa',
      );
    });

    test('abrir o caixa não planta o literal herdado no terminal', () async {
      final aberta = await abrir();
      // Sem caixa cadastrado o campo fica VAZIO; gravar o padrão do model aqui
      // era o que fazia a própria sessão carregar o nome enganoso adiante.
      expect('${aberta['station'] ?? ''}', isNot('PDV principal'));
    });
  });

  test('outra máquina não fecha nem movimenta a sessão', () async {
    final aberta = await abrir();
    stack.gateway.installationId = balcao02;

    await expectLater(
      stack.gateway.write(
        'POST',
        '/cash-register/${aberta['id']}/close/',
        body: {'actual_amount': '100.00', 'terminal_installation_id': balcao02},
      ),
      throwsA(isA<CashSessionConflict>()),
    );
    await expectLater(
      stack.gateway.write(
        'POST',
        '/cash-register/${aberta['id']}/withdrawal/',
        body: {
          'amount': '10.00',
          'reason': 'teste',
          'terminal_installation_id': balcao02,
        },
      ),
      throwsA(isA<CashSessionConflict>()),
    );
  });

  test('fechada, a sessão libera o caixa e some de current', () async {
    final aberta = await abrir();

    final fechada = await stack.gateway.write(
      'POST',
      '/cash-register/${aberta['id']}/close/',
      body: {'actual_amount': '100.00', 'terminal_installation_id': balcao01},
    );

    // A grafia é a do backend. Enquanto era `closed_difference`, uma sessão
    // fechada com diferença continuava "não finalizada" aqui — o caixa seguia
    // parecendo aberto e não podia ser reaberto.
    expect(
      CashSessionStatus.isFinished(fechada.payload['status']),
      isTrue,
      reason: '${fechada.payload['status']} deveria ser um estado final',
    );
    final atual = await stack.gateway.read('/cash-register/current/');
    expect(atual['_empty'], isTrue);

    final reaberta = await abrir();
    expect(reaberta['id'], isNot(aberta['id']));
  });

  test('fechamento com diferença usa o nome que o backend reconhece', () async {
    final aberta = await abrir();

    final fechada = await stack.gateway.write(
      'POST',
      '/cash-register/${aberta['id']}/close/',
      body: {'actual_amount': '90.00', 'terminal_installation_id': balcao01},
    );

    expect(
      fechada.payload['status'],
      CashSessionStatus.closedWithDifference,
    );
  });

  test('a grafia antiga gravada no disco ainda conta como finalizada', () {
    // Bases já existentes têm `closed_difference` gravado. Sem tolerar isso, o
    // caixa ficaria bloqueado até alguém limpar o SQLite do terminal.
    expect(CashSessionStatus.isFinished('closed_difference'), isTrue);
    expect(
      CashSessionStatus.normalize('closed_difference'),
      CashSessionStatus.closedWithDifference,
    );
  });
}
