import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import 'order_draft.dart';
import 'order_draft_cart.dart';
import 'order_merge_repository.dart';

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
    final commandId = draft.command?['id'];
    // Comanda: `open-command` RETOMA o pedido que já existe, então zero linha
    // nova é um caso legítimo — é o caixa cobrando exatamente o que o garçom
    // lançou. Sem comanda, o pedido nasce com o primeiro item, e sem item não
    // há o que nascer.
    if (commandId == null && draft.semLinhasNovas) {
      throw const ApiException('Não há itens para abrir o pedido.');
    }
    final linhas = draft.lines;

    final pedido = commandId == null
        ? await _criarComPrimeiroItem(draft, restaurantId: restaurantId)
        : await _abrirPelaComanda(draft);

    // Na comanda, TODOS os itens são acrescentados; no balcão, o primeiro já
    // entrou junto com o pedido.
    final restantes = commandId == null ? linhas.skip(1) : linhas;
    for (final linha in restantes) {
      await api.post(
        '/orders/${pedido['id']}/items/',
        body: linha.toItemPayload(),
        accessToken: accessToken,
      );
    }

    if (!draft.temVariasComandas) return pedido;
    return _agrupar(draft, primeiro: pedido);
  }

  /// A mesa com quatro cartões que paga junto.
  ///
  /// O pedido da PRIMEIRA comanda é a origem com que a consolidação é aberta;
  /// as outras entram depois. O destino é um pedido NOVO, criado pelo
  /// servidor — nunca o da primeira: ela também precisa preservar o pedido e
  /// os lotes dela, e ser origem e destino ao mesmo tempo duplicaria ou
  /// perderia itens e taxa.
  ///
  /// Quem decide se um cartão pode entrar é o SERVIDOR
  /// (`_assert_source_is_mergeable`): sem pedido aberto, sem itens, com
  /// recebimento lançado ou com nota emitida, ele recusa. A tela filtra o caso
  /// óbvio para dar a recusa na hora, mas a regra mora lá — e é lá que ela
  /// resiste a dois caixas fechando a mesma mesa ao mesmo tempo.
  Future<Map<String, dynamic>> _agrupar(
    OrderDraftCart draft, {
    required Map<String, dynamic> primeiro,
  }) async {
    // Pelo repositório, e não por caminhos escritos à mão aqui: as rotas da
    // consolidação já têm um dono, e duas cópias delas divergem na primeira
    // vez que uma mudar.
    final merges = OrderMergeRepository(api, accessToken: accessToken);

    final abertura = await merges.open('${primeiro['id']}');
    final mergeId = '${abertura['id'] ?? abertura['merge']?['id'] ?? ''}';
    if (mergeId.isEmpty) {
      throw const ApiException(
        'O servidor não devolveu a conta agrupada recém-aberta.',
      );
    }

    for (final comanda in draft.commands.skip(1)) {
      await merges.addCommand(
        mergeId,
        '${comanda['code'] ?? comanda['number'] ?? ''}',
      );
    }

    final confirmada = await merges.confirm(mergeId);
    final destino = confirmada['target_order'];
    if (destino is Map) return Map<String, dynamic>.from(destino);
    // O resumo sempre traz o destino; não vindo, seguir com o pedido da
    // primeira comanda cobraria só ela — melhor recusar do que cobrar menos.
    throw const ApiException(
      'A conta agrupada foi confirmada, mas o pedido de destino não veio na '
      'resposta. Abra a conta pela tela de pedidos para receber.',
    );
  }

  /// Comanda: `open-command` cria se o cartão está livre e RETOMA se já há
  /// pedido aberto nele.
  ///
  /// `create-with-item` não serve aqui: ele recusaria com "a comanda já está
  /// em uso" no caso normal de o garçom já ter lançado algo nela pelo
  /// aplicativo.
  Future<Map<String, dynamic>> _abrirPelaComanda(OrderDraftCart draft) async {
    final commandId = draft.command!['id'];
    final tableId = draft.table?['id'];
    if (tableId != null) {
      await api.post(
        '/commands/$commandId/link-table/',
        body: {'table_id': tableId},
        accessToken: accessToken,
      );
    }
    return await api.post(
      '/orders/open-command/',
      body: {'command': commandId},
      accessToken: accessToken,
    );
  }

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
