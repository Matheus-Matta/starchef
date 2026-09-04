import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';
import 'package:starchef_pdv/core/network/offline_mutations.dart';

/// Um Caixa Secundário **nunca fala com o servidor**.
///
/// Tudo o que ele faz passa pelo Caixa Principal: é o principal que tem o
/// SQLite da loja, a fila e o caminho até a nuvem. O que o secundário envia
/// junto são as credenciais DELE — para a operação chegar ao backend no nome
/// de quem realmente atendeu, e não no nome do principal.
///
/// Quando nem o principal responde, a operação é recusada na hora. Guardá-la
/// na fila do secundário seria admitir duas fontes de verdade durante uma
/// divisão de rede — exatamente como duas sessões do mesmo caixa nascem.
class _UnavailableRelay implements MutationRelay {
  int relayed = 0;

  @override
  Future<Map<String, dynamic>> relay(RelayMutation mutation) async {
    relayed += 1;
    throw const MutationRelayUnavailable('Caixa Principal fora de alcance.');
  }

  @override
  Future<bool> probe() async => false;

  @override
  Future<Map<String, dynamic>> read(RelayRead request) async {
    throw const MutationRelayUnavailable('Caixa Principal fora de alcance.');
  }
}

class _RecordingRelay implements MutationRelay {
  final List<RelayMutation> relayed = [];

  @override
  Future<Map<String, dynamic>> relay(RelayMutation mutation) async {
    relayed.add(mutation);
    return {'id': 'sessao-do-principal', 'status': 'open'};
  }

  @override
  Future<bool> probe() async => true;

  @override
  Future<Map<String, dynamic>> read(RelayRead request) async => const {};
}

void main() {
  group('o caixa passa pelo principal', () {
    test('abrir, fechar, sangrar e suprir são encaminhados', () {
      for (final path in [
        '/cash-register/open/',
        '/cash-register/00000000-0000-4000-8000-000000000000/close/',
        '/cash-register/00000000-0000-4000-8000-000000000000/withdrawal/',
        '/cash-register/00000000-0000-4000-8000-000000000000/supply/',
      ]) {
        expect(
          OfflineMutations.isRelayable('POST', path),
          isTrue,
          reason: '$path precisa chegar ao principal',
        );
      }
    });

    test('transferir e autorizar também, mesmo sem caber em fila', () {
      // Se o principal não pudesse executá-las, o secundário ficaria sem saída:
      // ele não tem permissão de falar com o servidor por conta própria.
      const transfer = '/cash-register/00000000-0000-4000-8000-000000000000/transfer/';
      expect(OfflineMutations.isRelayable('POST', transfer), isTrue);
      expect(OfflineMutations.isQueueable('POST', transfer), isFalse);
    });

    test('as operações que definem o dono continuam identificadas', () {
      expect(
        OfflineMutations.ownsCashSession('POST', '/cash-register/open/'),
        isTrue,
      );
      expect(
        OfflineMutations.ownsCashSession('POST', '/cash-register/s-1/close/'),
        isTrue,
      );
      // Sangria e suprimento exigem ser dono, mas não definem quem é.
      expect(
        OfflineMutations.ownsCashSession('POST', '/cash-register/s-1/supply/'),
        isFalse,
      );
    });
  });

  test('a abertura vai ao principal, e não à nuvem', () async {
    final relay = _RecordingRelay();
    // A nuvem responderia se alguém a chamasse — e ninguém deve chamar.
    var cloudCalls = 0;
    final api = ApiClient(baseUrl: 'http://127.0.0.1:9/api/v1')
      ..attachMutationRelay(relay);
    addTearDown(api.dispose);

    final result = await api.post(
      '/cash-register/open/',
      body: {'cash_station': 'caixa-1', 'opening_amount': '100.00'},
      accessToken: 'token',
    );

    expect(cloudCalls, 0);
    expect(result['id'], 'sessao-do-principal');
    expect(relay.relayed.single.path, '/cash-register/open/');
  });

  test('sem o principal, a abertura é recusada — não guardada', () async {
    final relay = _UnavailableRelay();
    final api = ApiClient(baseUrl: 'http://127.0.0.1:9/api/v1')
      ..attachMutationRelay(relay);
    addTearDown(api.dispose);

    await expectLater(
      api.post(
        '/cash-register/open/',
        body: {'cash_station': 'caixa-1', 'opening_amount': '100.00'},
        accessToken: 'token',
      ),
      throwsA(
        isA<ApiException>().having(
          (error) => error.message,
          'mensagem',
          contains('Caixa Principal'),
        ),
      ),
    );
    // Nada na fila deste terminal: a sessão é do principal, e uma cópia local
    // esperando para subir seria a segunda sessão que tudo isto evita.
    expect(await api.pendingOperations(), 0);
  });
}
