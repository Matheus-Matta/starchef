import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_exit.dart';

/// Sair da tela do pedido: três estados parecidos, consequências opostas.
///
/// O caso que motivou tudo: o caixa anexa os cartões, vai para o pagamento e
/// volta sem concluir. A conta não está vazia — tem as cópias das anotações —,
/// então ela não era descartada, e ficava aberta para sempre segurando o
/// consumo. A comanda mostrava os itens na tela e o servidor recusava cobrá-la
/// de novo, porque eles já pertenciam àquela conta.
///
/// E cancelar não era a saída: o cancelamento marca as anotações como PERDA. A
/// comida foi comida; quem desistiu foi a conta.
void main() {
  Map<String, dynamic> itemDeComanda({String comanda = 'c-1'}) => {
    'id': 'i-1',
    'status': 'pending',
    'command': comanda,
  };

  Map<String, dynamic> itemPassadoNoCaixa() => {
    'id': 'i-2',
    'status': 'pending',
    'command': null,
  };

  const aberto = {'id': 'o-1', 'status': 'open'};

  group('o que fazer ao sair', () {
    test('sem pedido nenhum, nada a fazer', () {
      expect(
        decideOrderExit(order: null, items: const [], hasPayments: false),
        OrderExit.keep,
      );
    });

    test('pedido vazio e descartado', () {
      expect(
        decideOrderExit(order: aberto, items: const [], hasPayments: false),
        OrderExit.discard,
      );
    });

    test('só itens de comanda: SOLTA os cartões', () {
      expect(
        decideOrderExit(
          order: aberto,
          items: [itemDeComanda(), itemDeComanda(comanda: 'c-2')],
          hasPayments: false,
        ),
        OrderExit.releaseCommands,
      );
    });

    test('item passado no caixa é venda: fica', () {
      expect(
        decideOrderExit(
          order: aberto,
          items: [itemDeComanda(), itemPassadoNoCaixa()],
          hasPayments: false,
        ),
        OrderExit.keep,
      );
    });

    test('recebimento registrado NUNCA é desfeito ao sair', () {
      // Dinheiro que entrou só sai pelo cancelamento de verdade, com motivo
      // e autorização.
      expect(
        decideOrderExit(
          order: aberto,
          items: [itemDeComanda()],
          hasPayments: true,
        ),
        OrderExit.keep,
      );
    });

    test('pedido pago não é tocado', () {
      expect(
        decideOrderExit(
          order: const {'id': 'o-1', 'status': 'paid'},
          items: const [],
          hasPayments: false,
        ),
        OrderExit.keep,
      );
    });

    test('item de comanda JÁ CANCELADO não segura a conta', () {
      // Só o que conta no total decide: uma conta em que tudo foi cancelado
      // não tem consumo para devolver a cartão nenhum.
      expect(
        decideOrderExit(
          order: aberto,
          items: [
            {'id': 'i-3', 'status': 'cancelled', 'command': 'c-1'},
          ],
          hasPayments: false,
        ),
        OrderExit.discard,
      );
    });
  });

  group('quais cartões devolver', () {
    test('sem repetir, mesmo com vários itens do mesmo cartão', () {
      final cartoes = commandsHeldBy([
        itemDeComanda(),
        itemDeComanda(),
        itemDeComanda(comanda: 'c-2'),
        itemPassadoNoCaixa(),
      ]);

      expect(cartoes, {'c-1', 'c-2'});
    });

    test('conta sem cartão nenhum devolve vazio', () {
      expect(commandsHeldBy([itemPassadoNoCaixa()]), isEmpty);
    });
  });
}
