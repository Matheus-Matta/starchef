import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/troco_so_em_dinheiro.dart';

/// O troco de cartão sai da gaveta sem nada ter entrado nela: um de R$ 50 num
/// débito deixou a nuvem R$ 50 acima da loja. O restaurante pode desligar.
void main() {
  const desligado = {'allow_change_on_non_cash': false};
  const debito = {'name': 'Cartão de débito', 'method_type': 'card'};

  test('desligado, o débito acima do restante é recusado com o máximo', () {
    expect(
      recusaDoTroco(
        restaurante: desligado,
        forma: debito,
        recebido: 100,
        restante: 50,
      ),
      'Este restaurante dá troco só em dinheiro: em Cartão de débito, '
      'receba no máximo R\$ 50,00.',
    );
  });

  test('desligado, o valor exato passa e o dinheiro continua dando troco', () {
    expect(
      recusaDoTroco(
        restaurante: desligado,
        forma: debito,
        recebido: 50,
        restante: 50,
      ),
      isNull,
    );
    expect(
      recusaDoTroco(
        restaurante: desligado,
        forma: const {'name': 'Dinheiro', 'method_type': 'cash'},
        recebido: 100,
        restante: 50,
      ),
      isNull,
    );
  });

  test('ligado, ou servidor antigo sem o campo, o débito dá troco', () {
    for (final restaurante in [
      const {'allow_change_on_non_cash': true},
      const <String, dynamic>{},
      null,
    ]) {
      expect(
        recusaDoTroco(
          restaurante: restaurante,
          forma: debito,
          recebido: 100,
          restante: 50,
        ),
        isNull,
      );
    }
  });
}
