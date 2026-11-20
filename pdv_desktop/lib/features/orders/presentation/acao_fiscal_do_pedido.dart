/// O que o botão fiscal do pedido faz, pela situação da nota.
///
/// Produção, 20/11/2026: a nota "aguardando a SEFAZ" deixava o botão apagado,
/// e a nota com erro só oferecia emitir — o cliente ia embora sem cupom. O
/// servidor já imprime a pendente em contingência (`/invoices/{id}/print/`
/// assina em tpEmis=9, `imprimir_aguardando.py`); faltava o PDV pedir.
///
/// A nota RECUSADA não vai direto para a contingência, e é de propósito: o
/// servidor só aceita contingência quando não consegue falar com a SEFAZ.
/// Recusa de cadastro sairia recusada de novo, com o cupom já na mão do
/// cliente. Ela é reenviada; se a SEFAZ não responder, sai em contingência.
library;

enum AcaoFiscal { imprimir, imprimirEmContingencia, reenviarEImprimir, emitir }

/// Notas que existem e ainda não foram autorizadas: imprimíveis em contingência.
const _pendentes = {
  'processing',
  'reconciliation_required',
  'awaiting_transmission',
  'contingency_pending',
};

/// A nota pendente que o operador pode imprimir já, em contingência.
bool notaPendente(Object? fiscalState) => _pendentes.contains('$fiscalState');

AcaoFiscal acaoFiscalDoPedido(Map<String, dynamic>? fiscal) {
  final estado = fiscal?['fiscal_state'];
  if (fiscal?['printable'] == true) return AcaoFiscal.imprimir;
  if (notaPendente(estado)) return AcaoFiscal.imprimirEmContingencia;
  if (estado == 'rejected' || estado == 'configuration_error') {
    return AcaoFiscal.reenviarEImprimir;
  }
  return AcaoFiscal.emitir;
}

/// A ação imprime uma nota que já existe (sem passar pelo `/invoices/emit/`).
bool acaoSoImprime(AcaoFiscal acao) =>
    acao == AcaoFiscal.imprimir || acao == AcaoFiscal.imprimirEmContingencia;

String rotuloDaAcaoFiscal(AcaoFiscal acao, {required bool ocupado}) {
  if (ocupado) {
    return acaoSoImprime(acao) ? 'Imprimindo DANFE...' : 'Emitindo NFC-e...';
  }
  return switch (acao) {
    AcaoFiscal.imprimir => 'Imprimir DANFE',
    AcaoFiscal.imprimirEmContingencia => 'Imprimir em contingência',
    AcaoFiscal.reenviarEImprimir => 'Reenviar e imprimir NFC-e',
    AcaoFiscal.emitir => 'Emitir NFC-e',
  };
}
