// A nota que ainda não foi autorizada também sai no papel.
//
// Produção, 20/11/2026: com a nota "aguardando a SEFAZ" o botão do pedido
// ficava apagado ("NFC-e aguardando a SEFAZ"), e com erro só oferecia emitir —
// o operador não tinha como entregar o cupom em contingência.
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/acao_fiscal_do_pedido.dart';

void main() {
  test('nota autorizada so imprime', () {
    final acao = acaoFiscalDoPedido({
      'printable': true,
      'fiscal_state': 'authorized',
    });
    expect(acao, AcaoFiscal.imprimir);
    expect(rotuloDaAcaoFiscal(acao, ocupado: false), 'Imprimir DANFE');
  });

  test(
    'nota aguardando a SEFAZ imprime em contingencia, sem emitir de novo',
    () {
      for (final estado in [
        'processing',
        'reconciliation_required',
        'awaiting_transmission',
      ]) {
        final acao = acaoFiscalDoPedido({
          'printable': false,
          'fiscal_state': estado,
        });
        expect(acao, AcaoFiscal.imprimirEmContingencia, reason: estado);
        expect(acaoSoImprime(acao), isTrue, reason: estado);
        expect(
          rotuloDaAcaoFiscal(acao, ocupado: false),
          'Imprimir em contingência',
        );
      }
    },
  );

  test(
    'nota com erro reenvia antes de imprimir: recusa nao vira contingencia',
    () {
      for (final estado in ['rejected', 'configuration_error']) {
        final acao = acaoFiscalDoPedido({
          'printable': false,
          'fiscal_state': estado,
        });
        expect(acao, AcaoFiscal.reenviarEImprimir, reason: estado);
        expect(acaoSoImprime(acao), isFalse, reason: estado);
        expect(notaPendente(estado), isFalse, reason: estado);
      }
    },
  );

  test('pedido sem nota emite', () {
    expect(acaoFiscalDoPedido(null), AcaoFiscal.emitir);
    expect(
      rotuloDaAcaoFiscal(AcaoFiscal.emitir, ocupado: true),
      'Emitindo NFC-e...',
    );
  });
}
