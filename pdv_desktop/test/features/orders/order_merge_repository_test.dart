import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_merge_repository.dart';

/// Os itens da conta agrupada precisam sair POR COMANDA.
///
/// Uma lista corrida de produtos responde "quanto deu"; ela não responde "de
/// quem é isto", que é a pergunta que o cliente faz quando quatro comandas
/// viram uma conta só — e é a conferência que pega o engano antes de virar
/// discussão no caixa.
void main() {
  Map<String, dynamic> item(
    String id,
    String comanda,
    int numero,
    String valor,
  ) => {
    'id': id,
    'command': comanda,
    'command_number': numero,
    'command_code': 'CMD-$numero',
    'product_name': 'Produto $id',
    'total_price': valor,
    'quantity': 1,
  };

  test('agrupa por comanda e soma o total de cada uma', () {
    final grupos = groupMergeItems({
      'items': [
        item('a', 'cmd-1', 13, '25.00'),
        item('b', 'cmd-2', 14, '10.00'),
        item('c', 'cmd-1', 13, '7.50'),
      ],
    });

    expect(grupos, hasLength(2));
    expect(grupos.first.number, 13);
    expect(grupos.first.items, hasLength(2));
    expect(grupos.first.total, closeTo(32.5, 0.001));
    expect(grupos.last.total, closeTo(10, 0.001));
  });

  test('ordena pelo numero IMPRESSO na comanda, nao pela ordem de chegada', () {
    final grupos = groupMergeItems({
      'items': [
        item('a', 'cmd-9', 21, '5.00'),
        item('b', 'cmd-1', 3, '5.00'),
      ],
    });

    expect(grupos.map((grupo) => grupo.number).toList(), [3, 21]);
  });

  test('conta vazia nao quebra a tela', () {
    expect(groupMergeItems(const {}), isEmpty);
    expect(groupMergeItems(const {'items': []}), isEmpty);
  });

  test('item sem comanda cai num grupo proprio em vez de sumir', () {
    final grupos = groupMergeItems({
      'items': [
        {'id': 'x', 'product_name': 'Avulso', 'total_price': '3.00'},
      ],
    });

    expect(grupos, hasLength(1));
    expect(grupos.first.commandId, isEmpty);
  });

  test('valor como numero e como texto dao o mesmo total', () {
    final texto = groupMergeItems({
      'items': [item('a', 'cmd-1', 1, '12.34')],
    });
    final numero = groupMergeItems({
      'items': [
        {...item('a', 'cmd-1', 1, ''), 'total_price': 12.34},
      ],
    });

    expect(texto.first.total, closeTo(numero.first.total, 0.001));
  });
}
