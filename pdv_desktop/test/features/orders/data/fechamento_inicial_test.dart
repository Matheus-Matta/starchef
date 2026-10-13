import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/data/fechamento_inicial.dart';

/// Uma simulação só para abrir o pagamento.
///
/// Mandar taxa, CPF ou cupom aqui sobrescreveria o padrão do pedido com um
/// palpite do PDV — e era para descobrir o padrão que a segunda simulação
/// existia (uns 3 s na nuvem).
void main() {
  test('nao chuta taxa, documento nem cupom: o servidor usa o do pedido', () {
    final fechamento = fechamentoInicial();
    expect(fechamento, {'discount': 0});
    for (final chave in [
      'service_fee_enabled',
      'fiscal_customer_cpf',
      'fiscal_customer_cnpj',
      'coupon_code',
    ]) {
      expect(fechamento.containsKey(chave), isFalse, reason: chave);
    }
  });

  test('cada chamada e um mapa novo: ajustar a tela nao altera o proximo', () {
    fechamentoInicial()['discount'] = 5;
    expect(fechamentoInicial()['discount'], 0);
  });
}
