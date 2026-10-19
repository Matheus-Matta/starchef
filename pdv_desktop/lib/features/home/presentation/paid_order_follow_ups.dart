import 'dart:async';

/// Libera o caixa antes de escolher a impressora e iniciar os efeitos da venda.
/// Recibo e NFC-e compartilham a escolha, mas não esperam um pelo outro.
///
/// [autoPrintReceipt] vem do cadastro do restaurante: desligado, o recibo não
/// sai sozinho (o botão "Imprimir recibo" continua valendo). A NFC-e não
/// depende dele — ela é obrigação fiscal, não preferência da loja.
///
/// [askDanfe] é o "Imprimir a NFC-e?" do restaurante que pergunta. Sai AGORA,
/// junto com a venda, e não depois da emissão: a resposta da emissão pode
/// levar a SEFAZ inteira, e o caixa ficava parado esperando o modal para
/// passar ao próximo cliente. A emissão não espera a resposta — recebe a
/// pergunta ainda aberta e só a consulta quando houver DANFE para imprimir.
void startPaidOrderFollowUps({
  required void Function() showNextSale,
  required Future<String?> Function() choosePrinter,
  required Future<void> Function(Future<String?> printer) printReceipt,
  required Future<void> Function(Future<String?> printer, Future<bool>? danfe)
  emitInvoice,
  required Future<void> Function() refreshCatalog,
  Future<bool> Function(Future<String?> printer)? askDanfe,
  bool autoPrintReceipt = true,
}) {
  showNextSale();
  final printer = choosePrinter();
  final danfe = askDanfe?.call(printer);
  if (autoPrintReceipt) unawaited(printReceipt(printer));
  unawaited(emitInvoice(printer, danfe));
  unawaited(refreshCatalog());
}
