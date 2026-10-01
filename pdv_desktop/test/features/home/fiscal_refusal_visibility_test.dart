import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/fiscal_refusal_visibility.dart';

void main() {
  test('a venda automatica mostra a recusa de uma nota criada', () {
    // `silentIfUnconfigured` cala somente restaurante que nao emite; uma nota
    // criada e recusada pela Focus exige acao do operador.
    expect(
      deveExibirRecusaFiscal({
        'id': 'nota-1',
        'emitted': false,
      }, silenciarSemConfiguracao: true),
      isTrue,
    );
  });

  test('a venda automatica cala restaurante sem emissao configurada', () {
    expect(
      deveExibirRecusaFiscal({
        'emitted': false,
      }, silenciarSemConfiguracao: true),
      isFalse,
    );
  });
}
