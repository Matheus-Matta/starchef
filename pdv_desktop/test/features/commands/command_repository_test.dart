import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';

/// "Em uso" é ter anotação PENDENTE, e não um campo de estado.
///
/// A comanda é um bloco de notas: ela não abre pedido. O que decide se o
/// cartão tem dono é ter o que cobrar — e a listagem manda a contagem
/// justamente para a grade não precisar abrir cada um.
void main() {
  test('comanda com valor a cobrar esta em uso', () {
    expect(
      comandaTemContaAberta({'pending_items': 3, 'pending_total': '42.00'}),
      isTrue,
    );
  });

  test('comanda sem nada pendente esta livre', () {
    expect(
      comandaTemContaAberta({'pending_items': 0, 'pending_total': '0.00'}),
      isFalse,
    );
  });

  test('comanda com item mas SEM VALOR nao entra numa conta', () {
    // Tudo cortesia: o cartão tem anotação, mas não acrescenta um centavo.
    // Anexá-lo produziria um pedido preso a um cartão que não cobra nada.
    expect(
      comandaTemContaAberta({'pending_items': 2, 'pending_total': '0.00'}),
      isFalse,
    );
  });

  test('cartao ja usado mas com tudo concluido volta a ficar livre', () {
    // O consumo continua no histórico; o que zerou foi o que há a cobrar.
    expect(
      comandaTemContaAberta({'pending_total': '0.00', 'status': 'free'}),
      isFalse,
    );
  });

  test('servidor antigo sem a contagem cai no retrato de estado', () {
    // O PDV pode estar falando com um backend anterior: sem o campo, o estado
    // gravado é a melhor resposta disponível — melhor que travar a tela.
    expect(comandaTemContaAberta({'status': 'occupied'}), isTrue);
    expect(comandaTemContaAberta({'status': 'free'}), isFalse);
    expect(comandaTemContaAberta(const {}), isFalse);
  });
}
