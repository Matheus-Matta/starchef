import '../../auth/domain/auth_session.dart';

/// O fechamento da venda NOVA calculado no PDV: taxa, desconto, CPF e total.
///
/// Cada toque em taxa, desconto ou CPF mandava a venda inteira ao servidor em
/// modo "simular" — criar o pedido, lançar cada item, anexar as comandas,
/// fechar e desfazer: 60 a 120 consultas por toque, com a tela travada em
/// "Calculando total". A conta é aritmética, e o PDV tem tudo o que ela pede.
///
/// O servidor continua sendo a autoridade: a conclusão leva o total mostrado
/// (`expected_total`) e ele recusa com 409 se não bater, e o PDV recalcula
/// (`total_mudou`). Para isso ser raro, a conta é a MESMA do servidor
/// (`orders/services.py`, `service_fee_for` e `recalculate_order`), conferida
/// pela tabela de casos que os dois testes leem.
///
/// Fica de fora o que só o banco sabe: o CUPOM (limite de usos, uso por CPF,
/// grupos) vai ao servidor, e o desconto dele chega aqui pronto
/// (`coupon_discount`), sendo mantido nas contas seguintes.
class FechamentoLocal {
  FechamentoLocal._();

  /// `pedido` com o fechamento refeito; lança [FechamentoRecusado] quando o
  /// servidor recusaria (desconto acima da conta, negativo).
  static Map<String, dynamic> aplicar(
    Map<String, dynamic> pedido,
    Map<String, dynamic> fechamento, {
    required String percentualDaTaxa,
  }) {
    final subtotal = centavos(pedido['subtotal']);
    final ligada = fechamento['service_fee_enabled'] != false;
    final desconto = centavos(fechamento['discount'] ?? pedido['discount']);
    final cupom = centavos(pedido['coupon_discount']);
    if (desconto < 0) {
      throw const FechamentoRecusado('O desconto não pode ser negativo.');
    }
    if (desconto + cupom > subtotal) {
      throw const FechamentoRecusado(
        'Desconto e cupom juntos passam do subtotal do pedido.',
      );
    }
    final taxa = ligada ? taxaDeServico(subtotal, percentualDaTaxa) : 0;
    final total =
        subtotal + taxa + centavos(pedido['delivery_fee']) - desconto - cupom;
    return {
      ...pedido,
      'service_fee_enabled': ligada,
      'service_fee': reais(taxa),
      'discount': reais(desconto),
      'coupon_discount': reais(cupom),
      if (fechamento.containsKey('fiscal_customer_cpf'))
        'fiscal_customer_cpf': fechamento['fiscal_customer_cpf'],
      if (fechamento.containsKey('fiscal_customer_cnpj'))
        'fiscal_customer_cnpj': fechamento['fiscal_customer_cnpj'],
      'total': reais(total < 0 ? 0 : total),
    };
  }

  /// `subtotal × percentual`, meio centavo para cima — o `ROUND_HALF_UP` do
  /// servidor. Em inteiros: 10,05 × 10% = 1,005 e vira 1,01 nos dois lados.
  static int taxaDeServico(int subtotal, String percentual) {
    final pontosBase = centavos(percentual); // 10.00% = 1000
    if (pontosBase <= 0 || subtotal <= 0) return 0;
    return (subtotal * pontosBase + 5000) ~/ 10000;
  }
}

/// O servidor recusaria este fechamento; `motivo` é a frase dele.
class FechamentoRecusado implements Exception {
  const FechamentoRecusado(this.motivo);
  final String motivo;

  @override
  String toString() => motivo;
}

/// Gerente para cima aprova o próprio desconto, sem senha — a mesma regra do
/// servidor (`discount_approval.py`, `has_role_at_least(user, "manager")`).
/// Errar para o lado de pedir a senha é seguro: o servidor confere de novo.
bool aprovaOProprioDesconto(AuthUser usuario) =>
    usuario.isSuperuser ||
    const {'manager', 'admin', 'owner'}.contains(usuario.profileType);

/// O total de UMA linha como o servidor grava: preço × quantidade (o peso em
/// 3 casas), meio centavo para cima (`add_order_item`).
///
/// Em `double` o PDV errava o centavo: R$ 49,90 × 0,750 kg = 37,425 vira
/// 37,42499… e saía 37,42, contra 37,43 do servidor — e a venda voltava
/// "total mudou". São mais de mil pares realistas de preço e peso assim.
int centavosDaLinha(double quantidade, double precoUnitario) {
  final milesimos = (quantidade * 1000).round();
  final preco = (precoUnitario * 100).round();
  return (milesimos * preco + 500) ~/ 1000;
}

/// Dinheiro em CENTAVOS inteiros: nunca `double` na conta (regra do projeto).
///
/// Aceita o texto do servidor ("27.50") e o número do carrinho, que soma em
/// `double` — ali o arredondamento para o centavo acontece na entrada.
int centavos(Object? valor) {
  if (valor == null) return 0;
  if (valor is int) return valor * 100;
  if (valor is double) return (valor * 100).round();
  final texto = '$valor'.trim();
  if (texto.isEmpty) return 0;
  final negativo = texto.startsWith('-');
  final partes = texto.replaceFirst('-', '').split('.');
  final inteiro = int.tryParse(partes[0].isEmpty ? '0' : partes[0]) ?? 0;
  final fracao = partes.length > 1 ? partes[1] : '';
  final dois = int.tryParse('${fracao}00'.substring(0, 2)) ?? 0;
  final arredonda = fracao.length > 2 && (int.tryParse(fracao[2]) ?? 0) >= 5
      ? 1
      : 0;
  final total = inteiro * 100 + dois + arredonda;
  return negativo ? -total : total;
}

/// Centavos de volta ao formato do servidor: "27.50".
String reais(int centavos) {
  final sinal = centavos < 0 ? '-' : '';
  final absoluto = centavos.abs();
  return '$sinal${absoluto ~/ 100}.${(absoluto % 100).toString().padLeft(2, '0')}';
}
