import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_commands.dart';

OrderDraftLine _linha({
  String produto = 'p1',
  String nome = 'Café',
  double quantidade = 1,
  double preco = 5,
  String? variacao,
  List<String> adicionais = const [],
  String nota = '',
  double? peso,
  String? leitura,
}) => OrderDraftLine(
  id: '',
  productId: produto,
  productName: nome,
  quantity: quantidade,
  unitPrice: preco,
  variationId: variacao,
  addonIds: adicionais,
  customerNote: nota,
  weightKg: peso,
  scaleReadingId: leitura,
);

void main() {
  group('o que o operador monta na tela', () {
    test('tres cafes iguais viram uma linha com quantidade tres', () {
      // Agrupar importa na conferência: três linhas iguais obrigam o operador
      // a contar com o dedo para saber quantos cafés vai cobrar.
      final carrinho = OrderDraftCart();
      carrinho.add(_linha());
      carrinho.add(_linha());
      carrinho.add(_linha());

      expect(carrinho.itemCount, 1);
      expect(carrinho.lines.single.quantity, 3);
      expect(carrinho.total, 15);
    });

    test('mesmo produto com observacoes diferentes NAO agrupa', () {
      // "sem açúcar" e "com açúcar" viram dois preparos na cozinha. Somá-los
      // numa linha só perderia a observação de um dos dois clientes.
      final carrinho = OrderDraftCart();
      carrinho.add(_linha(nota: 'sem açúcar'));
      carrinho.add(_linha(nota: 'com açúcar'));

      expect(carrinho.itemCount, 2);
    });

    test('dois cortes pesados nao viram um corte so', () {
      // 300 g + 300 g não é um corte de 600 g: cada pesagem tem a sua leitura
      // de balança, e juntá-las jogaria uma delas fora.
      final carrinho = OrderDraftCart();
      carrinho.add(_linha(peso: 0.3, quantidade: 0.3, leitura: 'r1'));
      carrinho.add(_linha(peso: 0.3, quantidade: 0.3, leitura: 'r2'));

      expect(carrinho.itemCount, 2);
    });

    test('baixar a quantidade ate zero tira a linha do carrinho', () {
      final carrinho = OrderDraftCart();
      carrinho.add(_linha());
      final id = carrinho.lines.single.id;

      carrinho.changeQuantity(id, 0);

      expect(carrinho.isEmpty, isTrue);
    });

    test('o total soma as linhas', () {
      final carrinho = OrderDraftCart();
      carrinho.add(_linha(preco: 5, quantidade: 2));
      carrinho.add(_linha(produto: 'p2', nome: 'Suco', preco: 7.5));

      expect(carrinho.total, 17.5);
    });
  });

  group('anexar comanda nao fala com o servidor', () {
    test('anexar leva o destino junto, e soltar volta para balcao', () {
      final carrinho = OrderDraftCart();
      expect(carrinho.orderType, 'counter');

      carrinho.attachCommand({'id': 'c1', 'number': 13}, at: {'id': 'm4'});
      expect(carrinho.orderType, 'command');
      expect(carrinho.command?['number'], 13);
      expect(carrinho.table?['id'], 'm4');

      // Soltar não desfaz nada lá fora porque nada foi feito lá fora — é só
      // tirar o cartão deste rascunho.
      carrinho.detachCommand();
      expect(carrinho.orderType, 'counter');
      expect(carrinho.command, isNull);
      expect(carrinho.table, isNull);
    });
  });

  group('o corpo que vai para a API', () {
    test('item pesado manda a leitura da balanca, nunca a quantidade', () {
      final corpo = _linha(
        quantidade: 0.42,
        peso: 0.42,
        leitura: 'r1',
      ).toItemPayload();

      expect(corpo['scale_reading'], 'r1');
      expect(corpo.containsKey('quantity'), isFalse);
      // O preço do pesado é por quilo e quem multiplica é o servidor: mandar
      // `expected_unit_price` aqui faria a conferência recusar a venda.
      expect(corpo.containsKey('expected_unit_price'), isFalse);
    });

    test('item pesado sem leitura manda o peso com tres casas', () {
      final corpo = _linha(quantidade: 0.42, peso: 0.42).toItemPayload();

      expect(corpo['weight_kg'], '0.420');
      expect(corpo.containsKey('scale_reading'), isFalse);
    });

    test('item comum manda quantidade e o preco de conferencia', () {
      final corpo = _linha(quantidade: 3, preco: 5).toItemPayload();

      expect(corpo['quantity'], 3);
      expect(corpo['expected_unit_price'], '5.00');
    });
  });

  group('o formato que o carrinho desenha', () {
    test('a linha chega como item pendente, que e o que ela e', () {
      // `pending` é o que o painel entende por "ainda não foi para a cozinha"
      // — a situação de toda linha de rascunho. Sem isso, o botão de enviar à
      // produção nasceria desligado.
      final item = _linha(quantidade: 2, preco: 5).toCartItem();

      expect(item['status'], 'pending');
      expect(item['total_price'], 10);
    });
  });

  group('limpar', () {
    test('esvaziar o rascunho apaga tambem o destino', () {
      // Um cartão que sobrasse aqui reapareceria anexado ao pedido SEGUINTE,
      // e o próximo cliente pagaria pela comanda do anterior.
      final carrinho = OrderDraftCart();
      carrinho.add(_linha());
      carrinho.attachCommand({'id': 'c1', 'number': 13});

      carrinho.clear();

      expect(carrinho.isEmpty, isTrue);
      expect(carrinho.command, isNull);
      expect(carrinho.orderType, 'counter');
    });
  });

  group('a comanda anexada traz a conta dela junto', () {
    const jaLancados = [
      {
        'id': 'i1',
        'product_name': 'Picanha',
        'quantity': 1,
        'total_price': 89.9,
      },
      {'id': 'i2', 'product_name': 'Chopp', 'quantity': 2, 'total_price': 24.0},
    ];

    test('o total soma o que ja estava na comanda com o que foi passado', () {
      // Era o buraco: anexar a comanda 3 mostrava carrinho vazio, sem o que o
      // garçom já tinha lançado nela pelo aplicativo.
      final carrinho = OrderDraftCart();
      carrinho.attachCommand({
        'id': 'c3',
        'number': 3,
      }, items: List<Map<String, dynamic>>.from(jaLancados));
      carrinho.add(_linha(preco: 6, quantidade: 1));

      expect(carrinho.commandTotal, closeTo(113.9, 0.001));
      expect(carrinho.total, closeTo(119.9, 0.001));
    });

    test('o carrinho mostra o lancado antes do que acabou de passar', () {
      final carrinho = OrderDraftCart();
      carrinho.attachCommand({
        'id': 'c3',
        'number': 3,
      }, items: List<Map<String, dynamic>>.from(jaLancados));
      carrinho.add(_linha(nome: 'Café'));

      final nomes = carrinho.cartItems
          .map((item) => item['product_name'])
          .toList();
      expect(nomes, ['Picanha', 'Chopp', 'Café']);
    });

    test('o item da comanda vai marcado como ja lancado', () {
      // A marca é o que impede o contador local de tentar editar um item que
      // vive no servidor — e falhar sem dizer nada.
      final carrinho = OrderDraftCart();
      carrinho.attachCommand({
        'id': 'c3',
        'number': 3,
      }, items: List<Map<String, dynamic>>.from(jaLancados));
      carrinho.add(_linha());

      final itens = carrinho.cartItems;
      expect(itens.first[OrderDraftCart.marcaDeJaLancado], isTrue);
      expect(itens.last[OrderDraftCart.marcaDeJaLancado], isNull);
    });

    test('comanda com conta e sem item novo AINDA tem o que cobrar', () {
      // O caixa cobrando exatamente o que o garçom lançou: o botão de
      // pagamento precisa estar aceso, e `isEmpty` é quem decide isso.
      final carrinho = OrderDraftCart();
      carrinho.attachCommand({
        'id': 'c3',
        'number': 3,
      }, items: List<Map<String, dynamic>>.from(jaLancados));

      expect(carrinho.isEmpty, isFalse);
      expect(carrinho.semLinhasNovas, isTrue);
      // Nada se perde ao sair: o que está na comanda continua no pedido dela.
      expect(carrinho.itemCount, 0);
    });

    test('soltar a comanda leva a conta dela embora', () {
      final carrinho = OrderDraftCart();
      carrinho.attachCommand({
        'id': 'c3',
        'number': 3,
      }, items: List<Map<String, dynamic>>.from(jaLancados));

      carrinho.detachCommand();

      expect(carrinho.commandItems, isEmpty);
      expect(carrinho.total, 0);
      expect(carrinho.isEmpty, isTrue);
    });
  });

  group('a mesa com varios cartoes que paga junto', () {
    Map<String, dynamic> comanda(String id, int numero) => {
      'id': id,
      'number': numero,
      'code': 'CMD-$numero',
    };

    List<Map<String, dynamic>> conta(double valor) => [
      {'id': 'i-$valor', 'product_name': 'Consumo', 'total_price': valor},
    ];

    test('quatro cartoes somam numa conta so', () {
      final carrinho = OrderDraftCart();
      carrinho.attachCommand(comanda('c1', 1), items: conta(30));
      carrinho.attachCommand(comanda('c2', 2), items: conta(20));
      carrinho.attachCommand(comanda('c3', 3), items: conta(15.5));

      expect(carrinho.commands.length, 3);
      expect(carrinho.temVariasComandas, isTrue);
      expect(carrinho.total, closeTo(65.5, 0.001));
    });

    test('passar o mesmo cartao de novo nao duplica', () {
      // O leitor dispara duas leituras com frequência. Virar duas linhas do
      // mesmo cartão cobraria a mesa duas vezes.
      final carrinho = OrderDraftCart();
      carrinho.attachCommand(comanda('c1', 1), items: conta(30));
      carrinho.attachCommand(comanda('c1', 1), items: conta(30));

      expect(carrinho.commands.length, 1);
      expect(carrinho.total, 30);
    });

    test('a mesa vem do PRIMEIRO cartao e nao troca no segundo', () {
      final carrinho = OrderDraftCart();
      carrinho.attachCommand(comanda('c1', 1), at: {'id': 'm4', 'number': 4});
      carrinho.attachCommand(comanda('c2', 2), at: {'id': 'm9', 'number': 9});

      expect(carrinho.table?['number'], 4);
    });

    test('soltar um de quatro NAO devolve o pedido ao balcao', () {
      final carrinho = OrderDraftCart();
      carrinho.attachCommand(comanda('c1', 1), items: conta(30));
      carrinho.attachCommand(comanda('c2', 2), items: conta(20));

      carrinho.detachCommand('c1');

      expect(carrinho.commands.length, 1);
      expect(carrinho.orderType, 'command');
      expect(carrinho.total, 20);
      // A conta do cartão solto vai embora junto: deixá-la somaria um valor
      // sem dono no total.
      expect(carrinho.commandItems.containsKey('c1'), isFalse);
    });

    test('soltar o ultimo volta para balcao', () {
      final carrinho = OrderDraftCart();
      carrinho.attachCommand(comanda('c1', 1), items: conta(30));

      carrinho.detachCommand('c1');

      expect(carrinho.orderType, 'counter');
      expect(carrinho.table, isNull);
      expect(carrinho.isEmpty, isTrue);
    });

    test('cada item diz de qual comanda veio', () {
      // Com quatro cartões na mesma conta, "quanto é a minha?" é a primeira
      // pergunta do cliente.
      final carrinho = OrderDraftCart();
      carrinho.attachCommand(comanda('c1', 1), items: conta(30));
      carrinho.attachCommand(comanda('c2', 2), items: conta(20));

      final donos = carrinho.cartItems
          .map((item) => item[OrderDraftCart.marcaDaComanda])
          .toList();
      expect(donos, ['1', '2']);
    });
  });
}
