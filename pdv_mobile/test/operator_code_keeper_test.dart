import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/features/orders/domain/operator_code_keeper.dart';

/// O código de quem lançou, num totem compartilhado.
///
/// O que estes testes fixam é a escolha central: o código vale por ATENDIMENTO.
/// Por item seria fiel e inutilizável (dez pratos, dez digitações, e a décima
/// vira "1111"); por sessão não serve num aparelho que passa de mão em mão.
void main() {
  test('guarda por atendimento, e cada um tem o seu', () {
    final guarda = OperatorCodeKeeper();

    guarda.guardar('comanda-12', '4821');
    guarda.guardar('comanda-30', '1002');

    expect(guarda.codigoDe('comanda-12'), '4821');
    expect(guarda.codigoDe('comanda-30'), '1002');
    // Atendimento que ninguém informou continua vazio: não herda do vizinho.
    expect(guarda.codigoDe('comanda-99'), '');
  });

  test('só dígitos entram — o servidor recusa letra de qualquer forma', () {
    final guarda = OperatorCodeKeeper();

    guarda.guardar('pedido-1', '48-21');
    expect(guarda.codigoDe('pedido-1'), '4821');

    // Nada de aproveitável: o código não é guardado, e a tela volta a pedir.
    guarda.guardar('pedido-2', 'joão');
    expect(guarda.temCodigo('pedido-2'), isFalse);
  });

  test('esquecer solta um atendimento sem tocar nos outros', () {
    final guarda = OperatorCodeKeeper();
    guarda.guardar('a', '1');
    guarda.guardar('b', '2');

    guarda.esquecer('a');

    expect(guarda.temCodigo('a'), isFalse);
    expect(guarda.codigoDe('b'), '2');
  });

  test('o corpo é null sem código, e não um mapa vazio', () {
    // O backend distingue "não informou" de "informou vazio": mandar `{}` num
    // restaurante que exige o código receberia a recusa sem o operador ter sido
    // perguntado — e ele veria um erro que não sabe resolver.
    final guarda = OperatorCodeKeeper();

    expect(guarda.corpoDe('pedido-1'), isNull);

    guarda.guardar('pedido-1', '777');
    expect(guarda.corpoDe('pedido-1'), {OperatorCodeKeeper.chave: '777'});
  });

  test('a chave é a mesma que o backend conhece', () {
    // Divergir aqui faria o código subir num campo que nenhum relatório lê, e o
    // rastro existiria sem nunca aparecer.
    expect(OperatorCodeKeeper.chave, 'operator_code');
  });

  test('limpar esvazia tudo — troca de sessão no aparelho', () {
    final guarda = OperatorCodeKeeper();
    guarda.guardar('a', '1');
    guarda.guardar('b', '2');

    guarda.limpar();

    expect(guarda.temCodigo('a'), isFalse);
    expect(guarda.temCodigo('b'), isFalse);
  });

  test('avisa quem escuta quando o código entra', () {
    final guarda = OperatorCodeKeeper();
    var avisos = 0;
    guarda.addListener(() => avisos++);

    guarda.guardar('a', '10');
    // Código recusado não avisa: nada mudou.
    guarda.guardar('b', 'abc');

    expect(avisos, 1);
  });
}
