import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../presentation/order_presenter.dart';
import 'order_draft_cart.dart';
import 'rastro_da_venda.dart';

/// A venda sai do PDV num envio só: `POST /orders/submit/`.
///
/// Até aqui o carrinho vive só na memória da tela — como num PDV de mercado,
/// onde passar produtos não abre nada em lugar nenhum. O pedido nasce quando
/// alguém de fora precisa dele: a COZINHA (Ctrl + E, que é também o "pagar depois")
/// ou a CONCLUSÃO da venda, que leva os recebimentos junto.
///
/// Antes eram uma chamada para criar o pedido, uma por item, uma para anexar
/// as comandas e uma por recebimento — e uma troca loja/nuvem no meio deixava
/// metade da venda em cada servidor. Agora é um payload, gravado numa
/// transação no servidor (`orders/venda_inteira.py`): entra inteiro ou não
/// entra. Tudo leva o UUID do PDV (`draft.orderId`, o id de cada linha), então
/// o reenvio depois de uma falha de rede é reconhecido como a MESMA venda.
class OrderDraftMaterializer {
  const OrderDraftMaterializer(this.api, {required this.accessToken});

  final ApiClient api;
  final String accessToken;

  static const caminho = '/orders/submit/';

  /// Faz o pedido EXISTIR com tudo o que está no rascunho. Devolve o pedido.
  ///
  /// `cozinha` manda à produção no mesmo envio (o Ctrl + E). O rascunho fica
  /// intacto em caso de falha: o operador não perde o que digitou.
  Future<Map<String, dynamic>> materialize(
    OrderDraftCart draft, {
    required String? restaurantId,
    bool cozinha = false,
  }) async {
    final resposta = await api.post(
      caminho,
      body: corpo(draft, restaurantId: restaurantId, cozinha: cozinha),
      accessToken: accessToken,
    );
    return Map<String, dynamic>.from(resposta['order'] as Map);
  }

  /// O total OFICIAL (taxa, promoção, cupom) sem gravar nada — para a tela de
  /// pagamento, enquanto o pedido ainda vive só no PDV.
  Future<Map<String, dynamic>> simular(
    OrderDraftCart draft, {
    required String? restaurantId,
    Map<String, dynamic>? fechamento,
    String? senhaDoCaixa,
  }) async {
    final resposta = await api.post(
      caminho,
      body: {
        ...corpo(draft, restaurantId: restaurantId, fechamento: fechamento),
        'simular': true,
        // Aprova o desconto de quem não é gerente, como no `/close/`.
        'cash_password': ?senhaDoCaixa,
      },
      accessToken: accessToken,
    );
    return Map<String, dynamic>.from(resposta['order'] as Map);
  }

  /// Conclui a venda: pedido, cozinha, fechamento e recebimentos num envio.
  ///
  /// Devolve `{order, payments}` do servidor.
  Future<Map<String, dynamic>> concluir(
    OrderDraftCart draft, {
    required String? restaurantId,
    Map<String, dynamic>? fechamento,
    required List<Map<String, dynamic>> recebimentos,
    String? totalMostrado,
    String? senhaDoCaixa,
  }) => comRastro(
    'venda',
    pedido: draft.orderId,
    dados: {'total': totalMostrado, 'recebimentos': recebimentos.length},
    chamada: () => api.post(
      caminho,
      body: {
        ...corpo(
          draft,
          restaurantId: restaurantId,
          cozinha: true,
          fechamento: fechamento,
        ),
        'payments': recebimentos,
        // O total que o cliente viu: mudou no servidor (parte da comanda foi
        // cobrada em outra conta), a venda é recusada sem gravar nada.
        'expected_total': ?totalMostrado,
        'cash_password': ?senhaDoCaixa,
      },
      accessToken: accessToken,
    ),
  );

  /// Os recebimentos de um pedido que JÁ existe, todos num envio só.
  Future<Map<String, dynamic>> receber({
    required String orderId,
    required String? restaurantId,
    required List<Map<String, dynamic>> recebimentos,
  }) => comRastro(
    'recebimento',
    pedido: orderId,
    dados: {'recebimentos': recebimentos.length},
    chamada: () => api.post(
      caminho,
      body: {
        'id': orderId,
        'restaurant': restaurantId,
        'items': const <Map<String, dynamic>>[],
        'payments': recebimentos,
      },
      accessToken: accessToken,
    ),
  );

  /// O corpo da venda inteira, a partir do rascunho.
  Map<String, dynamic> corpo(
    OrderDraftCart draft, {
    required String? restaurantId,
    bool cozinha = false,
    Map<String, dynamic>? fechamento,
  }) {
    // Sem item E sem comanda não há o que abrir. Com um dos dois, há: a mesa
    // com dois cartões que chega no caixa não tem nada novo para passar.
    if (draft.isEmpty) {
      throw const ApiException(
        'Não há itens nem comandas para abrir o pedido.',
      );
    }
    return {
      'id': draft.orderId,
      // Com cartão anexado o pedido é de comanda, mesmo com itens novos junto:
      // é o que a tela web grava, e o relatório agrupa por tipo.
      'order_type': draft.commands.isEmpty ? draft.orderType : 'command',
      'restaurant': restaurantId,
      if (draft.customer != null) 'customer': draft.customer!['id'],
      'items': [for (final linha in draft.lines) linha.toItemPayload()],
      'commands': [for (final comanda in draft.commands) '${comanda['id']}'],
      'command_items': ?draft.anotacoesVistas,
      if (cozinha)
        'kitchen': {
          'client_batch_serial': OrderPresenter.generateBatchSerial(),
        },
      'close': ?fechamento,
    };
  }
}
