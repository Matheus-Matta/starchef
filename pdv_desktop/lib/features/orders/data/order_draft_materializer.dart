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
    // O pedido nasce com o primeiro item, e sem item não há o que nascer.
    // Mesmo cobrando só comandas é preciso UM item para o pedido existir — por
    // isso a tela exige que algo seja passado antes de fechar a conta.
    if (draft.semLinhasNovas) {
      throw const ApiException('Não há itens para abrir o pedido.');
    }

    // `create-with-item` é atômico: uma falha no meio não deixa pedido vazio.
    final pedido = await _criarComPrimeiroItem(draft, restaurantId: restaurantId);
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
        'order_type': draft.orderType,
        'restaurant': restaurantId,
        if (draft.customer != null) 'customer': draft.customer!['id'],
        'item': primeiro.toItemPayload(),
      },
      accessToken: accessToken,
    );
  }
}
