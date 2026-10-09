import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/orders_presenter.dart';

/// "Pedidos abertos" mostrava pedido que não tinha nada: aberto e abandonado,
/// ou com todos os itens cancelados. Para o garçom, isso é um pedido que não
/// existe — e ele perdia tempo abrindo para conferir.
void main() {
  Map<String, dynamic> pedido(String id, List<String> statusDosItens) => {
    'id': id,
    'items': [
      for (final status in statusDosItens) {'status': status},
    ],
  };

  test('some o pedido sem nenhum item ativo', () {
    final visiveis = pedidosComConteudo([
      pedido('vazio', []),
      pedido('todo-cancelado', ['cancelled', 'comped']),
      pedido('com-item', ['cancelled', 'sent']),
      pedido('so-pendente', ['pending']),
    ]);

    expect(visiveis.map((p) => p['id']), ['com-item', 'so-pendente']);
  });

  test('pedido sem a lista de itens na resposta continua aparecendo', () {
    // Na dúvida, mostra: esconder um pedido de verdade é pior que um a mais.
    expect(
      pedidosComConteudo([
        {'id': 'x'},
      ]),
      hasLength(1),
    );
  });
}
