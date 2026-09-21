import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/sync/pending_mutation.dart';
import 'package:starchef_pdv_mobile/features/orders/data/order_subject.dart';

/// A comanda usa a MESMA tela do pedido. Estas são as regras que fazem isso
/// funcionar sem mentir sobre o que a comanda é.
void main() {
  PendingMutation mutacao(String method, String path, String kind) =>
      PendingMutation(
        operationId: 'op-1',
        method: method,
        path: path,
        kind: kind,
        summary: 'x',
        createdAt: DateTime(2026),
      );

  group('a fila offline enxerga a comanda', () {
    test('uma anotacao na comanda pertence AQUELA comanda', () {
      // A regra que fazia falta. Enquanto só `/orders/` era reconhecido, a
      // anotação lançada sem rede subia mas não aparecia em lugar nenhum da
      // comanda: sem selo de "aguardando conexão", e sem entrar na lista de
      // recusados — um item que o backend rejeitasse sumia sem deixar rastro.
      final m = mutacao('POST', '/commands/c-7/items/', 'add_item');

      expect(m.subjectId, 'c-7');
    });

    test('o cancelamento de uma anotacao aponta para o item certo', () {
      // É por este id que o item ganha o selo de "cancelando" enquanto o
      // backend não confirma.
      final m = mutacao('DELETE', '/commands/c-7/items/i-3/void/', 'void_item');

      expect(m.subjectId, 'c-7');
      expect(m.itemId, 'i-3');
    });

    test('o pedido continua funcionando como antes', () {
      final m = mutacao('DELETE', '/orders/o-1/items/i-9/void/', 'void_item');

      expect(m.subjectId, 'o-1');
      expect(m.itemId, 'i-9');
    });

    test('o pedido criado offline responde pelo id provisorio', () {
      // O caminho ainda é `/orders/`, mas o id de lá não existe: quem manda é
      // o provisório, que é por onde a tela acha o pedido até sincronizar.
      final m = PendingMutation(
        operationId: 'op-2',
        method: 'POST',
        path: '/orders/',
        kind: 'create_order',
        summary: 'Novo pedido',
        createdAt: DateTime(2026),
        placeholderOrderId: 'offline-abc',
      );

      expect(m.subjectId, 'offline-abc');
    });
  });

  group('a comanda lida como pedido', () {
    final resposta = {
      'command': {
        'id': 'c-7',
        'number': 12,
        'current_table': 't-4',
        'current_table_number': '4',
        'customer_name': 'Ana',
        'pending_total': '48.50',
        'pending_items': 3,
      },
      'items': [
        {'id': 'i-1', 'product_name': 'Coxinha', 'status': 'sent'},
        {'id': 'i-2', 'product_name': 'Guaraná', 'status': 'pending'},
      ],
    };

    test('traz numero, mesa e as anotacoes', () {
      final subject = commandAsSubject(resposta);

      expect(subject['command_number'], 12);
      expect(subject['table_number'], '4');
      expect((subject['items'] as List).length, 2);
    });

    test('o total e o PENDENTE, nao o historico', () {
      // É o que a comanda deve AGORA, que é a pergunta do garçom. O cartão
      // reutilizado traria a conta do cliente anterior.
      expect(commandAsSubject(resposta)['total'], '48.50');
    });

    test('a comanda NAO chega a esperar pagamento', () {
      // É isso que mantém o botão de receber fora da tela: cobrar é do caixa,
      // que puxa as anotações pendentes para um pedido.
      expect(commandAsSubject(resposta)['status'], 'open');
    });

    test('o vinculo de mesa aponta para a PROPRIA comanda', () {
      // No pedido, `command` é a comanda vinculada a ele. Aqui o assunto é ela
      // mesma — e é por este campo que o botão de mesa sabe o que vincular.
      final subject = commandAsSubject(resposta);

      expect(subject['command'], 'c-7');
      expect(subject['table'], 't-4');
    });

    test('resposta sem comanda nao quebra a tela', () {
      final subject = commandAsSubject(const {});

      expect(subject['items'], isEmpty);
      expect(subject['total'], isNull);
    });
  });

  group('a comanda na lista da tela inicial', () {
    final linha = {
      'id': 'c-7',
      'number': 12,
      'pending_items': 3,
      'pending_total': '48.50',
      'current_table_number': '4',
    };

    test('a contagem vem da listagem, nao dos itens', () {
      // `/commands/` não traz os itens de cada cartão de propósito: desenhar
      // um salão cheio custaria uma consulta por comanda.
      expect(itemCountOf(linha), 3);
      expect(commandRowAsSubject(linha)['items'], isEmpty);
    });

    test('comanda sem contagem conhecida conta zero', () {
      expect(itemCountOf(const {}), 0);
    });

    test('a linha carrega numero e total para o cartao', () {
      final subject = commandRowAsSubject(linha);

      expect(subject['command_number'], 12);
      expect(subject['total'], '48.50');
      expect(subject['order_type'], 'command');
    });
  });

  group('o que a comanda nao faz', () {
    test('comanda nao se cobra no aparelho', () {
      expect(const OrderSubject.command('c-7').canBeCharged, isFalse);
      expect(const OrderSubject.command('c-7').isCommand, isTrue);
    });

    test('pedido se cobra', () {
      expect(const OrderSubject.order('o-1').canBeCharged, isTrue);
      expect(const OrderSubject.order('o-1').isCommand, isFalse);
    });

    test('comanda e pedido de mesmo id sao assuntos DIFERENTES', () {
      // Os dois ids vêm de tabelas diferentes e podem coincidir. Tratá-los
      // como iguais faria a tela buscar um no endereço do outro.
      expect(
        const OrderSubject.command('x'),
        isNot(const OrderSubject.order('x')),
      );
    });
  });
}
