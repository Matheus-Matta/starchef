/// Troco só em dinheiro, quando o restaurante desliga
/// `allow_change_on_non_cash`.
///
/// É a mesma regra do servidor (`backend/apps/payments/troco.py`), conferida
/// AQUI para o caixa ver o aviso antes de concluir: cartão, PIX e voucher não
/// passam do restante. Sem o campo (servidor antigo), vale o de antes: qualquer
/// forma dá troco. Devolve o aviso, ou `null` quando pode.
String? recusaDoTroco({
  required Map<String, dynamic>? restaurante,
  required Map<String, dynamic> forma,
  required double recebido,
  required double restante,
}) {
  if (forma['method_type'] == 'cash') return null;
  if (restaurante?['allow_change_on_non_cash'] != false) return null;
  if (recebido <= restante + .009) return null;
  final maximo = restante.toStringAsFixed(2).replaceAll('.', ',');
  return 'Este restaurante dá troco só em dinheiro: em ${forma['name']}, '
      'receba no máximo R\$ $maximo.';
}
