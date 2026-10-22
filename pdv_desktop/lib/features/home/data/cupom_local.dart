import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';
import '../../orders/data/order_draft_cart.dart';
import 'fechamento_local.dart';

/// O cupom da venda NOVA: o servidor confere, o PDV faz a conta.
///
/// Digitar um cupom simulava a venda inteira no servidor — criar o pedido,
/// lançar cada item, fechar e desfazer, 60 a 120 consultas — só para saber o
/// desconto. Agora vai só a pergunta que precisa do banco (o cupom venceu,
/// esgotou, este CPF já usou?), com os números da venda
/// (`coupon_sem_pedido.py`); o desconto que volta entra no fechamento local
/// (`fechamento_local.dart`). A conclusão aplica o cupom de verdade e confere o
/// total (`expected_total`), como já faz com taxa e desconto.
class CupomRecusado implements Exception {
  const CupomRecusado(this.motivo);

  final String motivo;

  @override
  String toString() => motivo;
}

/// O servidor ainda não confere cupom SEM pedido (backend anterior a esta
/// conferência): ele respondia 400 "Informe o pedido a conferir.". Quem
/// chama volta à simulação no servidor, que funciona em qualquer versão — o
/// PDV atualizado não pode depender de o servidor ter sido atualizado antes.
class ConferenciaSemPedidoIndisponivel implements Exception {
  const ConferenciaSemPedidoIndisponivel();
}

/// O pedido da tela com o cupom [codigo] conferido e o total refeito.
///
/// Código vazio RETIRA o cupom, sem ir ao servidor. Recusado, lança
/// [CupomRecusado] com a frase do servidor ("Este CPF já usou este cupom").
Future<Map<String, dynamic>> aplicarCupomLocal(
  ApiClient api, {
  required String accessToken,
  required String codigo,
  required Map<String, dynamic> pedido,
  required Map<String, dynamic> fechamento,
  required OrderDraftCart draft,
  required String percentualDaTaxa,
  String? restaurantId,
}) async {
  var codigoAceito = '';
  var desconto = '0.00';
  if (codigo.trim().isNotEmpty) {
    final resposta = await _conferir(api, accessToken, {
      'code': codigo.trim(),
      'subtotal': '${pedido['subtotal'] ?? '0.00'}',
      'delivery_fee': '${pedido['delivery_fee'] ?? '0.00'}',
      'order_type': draft.orderType,
      'cpf': '${pedido['fiscal_customer_cpf'] ?? ''}',
      'products': produtosDaVenda(draft),
      'restaurant': ?restaurantId,
    });
    if (resposta['valid'] != true) {
      throw CupomRecusado('${resposta['reason'] ?? 'Cupom recusado.'}');
    }
    codigoAceito = '${(resposta['coupon'] as Map?)?['code'] ?? codigo}';
    desconto = reais(centavos(resposta['discount']));
  }
  return FechamentoLocal.aplicar(
    {...pedido, 'coupon_code': codigoAceito, 'coupon_discount': desconto},
    fechamento,
    percentualDaTaxa: percentualDaTaxa,
  );
}

Future<Map<String, dynamic>> _conferir(
  ApiClient api,
  String accessToken,
  Map<String, dynamic> body,
) async {
  try {
    return await api.post(
      '/promotions/coupons/validate/',
      body: body,
      accessToken: accessToken,
    );
  } on ApiException catch (erro) {
    // Com os números da venda sempre presentes, 400 aqui só sai do servidor
    // que exige pedido salvo.
    if (erro.statusCode == 400) throw const ConferenciaSemPedidoIndisponivel();
    rethrow;
  }
}

/// Os produtos da venda: os passados agora e os que já estavam na comanda.
/// O cupom que não acumula com promoção precisa saber quais são.
List<String> produtosDaVenda(OrderDraftCart draft) => {
  for (final linha in draft.lines) linha.productId,
  for (final item in draft.itensJaLancados)
    if (item['product'] != null) '${item['product']}',
}.toList();
