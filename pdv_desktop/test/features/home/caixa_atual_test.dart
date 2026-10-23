import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/home/data/caixa_atual.dart';

void main() {
  const aberto = <String, dynamic>{'id': 'c1', 'status': 'open'};

  test('caixa fechado em outro aviso apaga a sessão e volta o bloqueio', () {
    // O aviso de caixa passou a reler só `/cash-register/current/`; o 404
    // ("nenhum caixa aberto") era engolido e a sessão fechada continuava na
    // tela, sem a tela "Abra o caixa para iniciar".
    expect(
      caixaAposRecusa(const ApiException('x', statusCode: 404), aberto),
      isNull,
    );
  });

  test('caixa com outra pessoa ou outra máquina também não é deste terminal', () {
    for (final codigo in const [403, 409]) {
      expect(
        caixaAposRecusa(ApiException('x', statusCode: codigo), aberto),
        isNull,
      );
    }
  });

  test('queda de rede não fecha o caixa na tela', () {
    // Sem resposta do servidor ninguém sabe o estado: a tela segue como
    // estava, e não trava o operador no meio da venda.
    expect(
      caixaAposRecusa(
        const ApiException('x', isConnectivity: true),
        aberto,
      ),
      same(aberto),
    );
    expect(
      caixaAposRecusa(const ApiException('x', statusCode: 500), aberto),
      same(aberto),
    );
  });
}
