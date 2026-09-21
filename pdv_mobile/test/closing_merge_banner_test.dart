import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/closing_merge_banner.dart';

/// "Em fechamento" só vale para a comanda que é ORIGEM de uma conta agrupada.
///
/// O pedido de DESTINO também carrega `closing_merge`, e ele é o oposto: é a
/// conta que o caixa está cobrando. Tratar os dois igual esconderia do caixa
/// a própria conta que ele acabou de montar.
void main() {
  test('comanda de origem esta em fechamento', () {
    expect(
      ClosingMergeBanner.isClosing({
        'closing_merge': {'id': 'm1', 'role': 'source', 'status': 'open'},
      }),
      isTrue,
    );
  });

  test('o pedido de destino NAO esta em fechamento — ele e a conta', () {
    expect(
      ClosingMergeBanner.isClosing({
        'closing_merge': {'id': 'm1', 'role': 'target', 'status': 'confirmed'},
      }),
      isFalse,
    );
  });

  test('pedido comum nao tem consolidacao nenhuma', () {
    expect(ClosingMergeBanner.isClosing({'closing_merge': null}), isFalse);
    expect(ClosingMergeBanner.isClosing({}), isFalse);
    expect(ClosingMergeBanner.isClosing(null), isFalse);
  });

  test('cliente antigo que mandar so o id nao trava a tela', () {
    expect(ClosingMergeBanner.isClosing({'closing_merge': 'merge-1'}), isFalse);
  });
}
