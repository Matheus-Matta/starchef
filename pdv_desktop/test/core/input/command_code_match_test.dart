import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/input/command_code_match.dart';

/// O cartão 17 lido não pode abrir a comanda 107.
///
/// O defeito da loja: a aba Comandas, sem casamento exato, abria "a única
/// comanda que sobrou na lista filtrada". Com a busca guardando um texto
/// antigo, a leitura de `0017` abriu a 107.
void main() {
  final comanda17 = {'id': 'c17', 'number': 17, 'code': '0017'};
  final comanda107 = {'id': 'c107', 'number': 107, 'code': '0107'};

  test('o código impresso com zeros casa com o número da comanda', () {
    expect(comandaCasaComLido(comanda17, '0017'), isTrue);
    expect(comandaCasaComLido(comanda17, '17'), isTrue);
    expect(comandaCasaComLido({'number': 17, 'code': ''}, '0017'), isTrue);
  });

  test('17 lido nunca casa com a comanda 107', () {
    expect(comandaCasaComLido(comanda107, '0017'), isFalse);
    expect(comandaCasaComLido(comanda107, '17'), isFalse);
    expect(comandaCasaComLido(comanda107, '107'), isTrue);
  });

  test(
    'a escolha na lista é só por casamento exato, nunca a única restante',
    () {
      // A lista filtrada sobrou com uma só comanda — e ela não é a lida.
      expect(comandaLidaNaLista([comanda107], '0017'), isNull);
      expect(
        comandaLidaNaLista([comanda107, comanda17], '0017'),
        same(comanda17),
      );
    },
  );

  test('código customizado não numérico casa só por igualdade', () {
    final vip = {'number': 5, 'code': 'VIP-05'};
    expect(comandaCasaComLido(vip, 'VIP-05'), isTrue);
    expect(comandaCasaComLido(vip, 'VIP-5'), isFalse);
    expect(comandaCasaComLido(vip, '5'), isTrue);
  });

  test('o número mostrado na tela é o lido, sem os zeros da etiqueta', () {
    expect(numeroLidoParaExibir(' 0017 '), '17');
    expect(numeroLidoParaExibir('0000'), '0');
    expect(numeroLidoParaExibir('VIP-05'), 'VIP-05');
  });
}
