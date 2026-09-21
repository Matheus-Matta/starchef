import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import 'order_draft.dart';
import 'order_draft_cart.dart';

/// Materializar um rascunho: a hora em que o pedido precisa passar a EXISTIR.
///
/// Até aqui o carrinho vive só na memória da tela — como num PDV de mercado,
/// onde passar produtos não abre nada em lugar nenhum. O pedido nasce quando
/// alguém de fora precisa dele:
///
/// * a **cozinha**, que vai imprimir um ticket e produzir;
/// * o **caixa**, que vai anexar um recebimento.
///
/// Criar antes disso enche o banco de pedidos vazios e prende comandas que
/// ninguém está usando. Este arquivo é o irmão de `orderDraftService.js` da
/// web, e as duas telas mandam o mesmo corpo para os mesmos endpoints — uma
/// divergência aqui viraria um pedido com formato diferente conforme o caixa
/// em que foi aberto.
class OrderDraftMaterializer {
  const OrderDraftMaterializer(this.api, {required this.accessToken});

  final ApiClient api;
  final String accessToken;

  /// Cria (ou retoma) o pedido e põe todos os itens do rascunho dentro dele.
  ///
  /// Devolve o pedido do servidor e propaga a exceção da API para quem chamou
  /// decidir: o rascunho fica intacto na tela, então uma falha de rede não
  /// custa ao operador o que ele já digitou.
  Future<Map<String, dynamic>> materialize(
    OrderDraftCart draft, {
    required String? restaurantId,
  }) async {
    // Sem item E sem comanda não há o que abrir. Com um dos dois, há.
    //
    // Exigir um item mesmo cobrando só comandas quebrava o caso CENTRAL do
    // modelo novo: a mesa com dois cartões que chega no caixa para pagar. O
    // operador não tem nada para passar — o consumo já está anotado nos
    // cartões —, e a conta simplesmente não abria.
    if (draft.isEmpty) {
      throw const ApiException('Não há itens nem comandas para abrir o pedido.');
    }

    // `create-with-item` é atômico: uma falha no meio não deixa pedido vazio.
    // Sem item nenhum ele não serve, e aí o pedido nasce vazio mesmo — o que
    // o enche em seguida são as anotações das comandas.
    final pedido = draft.semLinhasNovas
        ? await _criarParaComandas(draft, restaurantId: restaurantId)
        : await _criarComPrimeiroItem(draft, restaurantId: restaurantId);
    for (final linha in draft.lines.skip(1)) {
      await api.post(
        '/orders/${pedido['id']}/items/',
        body: linha.toItemPayload(),
        accessToken: accessToken,
      );
    }

    if (draft.commands.isEmpty) return pedido;
    return _puxarComandas(draft, pedido: pedido);
  }

  /// A mesa com quatro cartões que paga junto.
  ///
  /// A comanda não abre pedido — ela ANOTA. O pedido do caixa puxa as
  /// anotações PENDENTES dos cartões, e isso é UMA chamada, não uma por
  /// cartão: duzentas idas ao servidor com o cliente esperando.
  ///
  /// Quem decide se um cartão pode entrar é o SERVIDOR: sem item pendente ele
  /// recusa. A tela filtra o caso óbvio para dar a recusa na hora, mas a regra
  /// mora lá — e é lá que ela resiste a dois caixas fechando a mesma mesa ao
  /// mesmo tempo.
  Future<Map<String, dynamic>> _puxarComandas(
    OrderDraftCart draft, {
    required Map<String, dynamic> pedido,
  }) => api.post(
    '/orders/${pedido['id']}/attach-commands/',
    body: {
      'commands': [for (final comanda in draft.commands) '${comanda['id']}'],
    },
    accessToken: accessToken,
  );

  /// Só comandas: o pedido nasce VAZIO e as anotações o preenchem.
  ///
  /// É o caminho da mesa que chega no caixa sem nada novo para passar. O
  /// `create-with-item` não serve aqui porque não há item; o pedido vazio dura
  /// o tempo de uma chamada, até `attach-commands` puxar o que os cartões
  /// anotaram.
  ///
  /// `order_type` é `command` — igual ao que a tela web manda no mesmo caso.
  /// Os dois PDVs precisam gravar o mesmo formato: um pedido com tipo
  /// diferente conforme o caixa em que foi aberto quebra qualquer relatório
  /// que agrupe por tipo.
  Future<Map<String, dynamic>> _criarParaComandas(
    OrderDraftCart draft, {
    required String? restaurantId,
  }) => api.post(
    '/orders/',
    body: {
      'order_type': 'command',
      'restaurant': restaurantId,
      if (draft.customer != null) 'customer': draft.customer!['id'],
    },
    accessToken: accessToken,
  );

  /// Balcão, entrega e retirada: o pedido nasce COM o primeiro item.
  ///
  /// `create-with-item` é atômico — pedido e item na mesma transação. É o que
  /// garante que uma falha no meio não deixe um pedido vazio para trás.
  Future<Map<String, dynamic>> _criarComPrimeiroItem(
    OrderDraftCart draft, {
    required String? restaurantId,
  }) async {
    final OrderDraftLine primeiro = draft.lines.first;
    return await api.post(
      '/orders/create-with-item/',
      body: {
        // Com cartão anexado o pedido é de comanda, mesmo que o operador tenha
        // passado itens novos junto. É o que a tela web já fazia.
        'order_type': draft.commands.isEmpty ? draft.orderType : 'command',
        'restaurant': restaurantId,
        if (draft.customer != null) 'customer': draft.customer!['id'],
        'item': primeiro.toItemPayload(),
      },
      accessToken: accessToken,
    );
  }
}
