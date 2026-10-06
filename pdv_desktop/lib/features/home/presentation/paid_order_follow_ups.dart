import 'dart:async';

/// Libera o caixa antes de escolher a impressora e iniciar os efeitos da venda.
/// Recibo e NFC-e compartilham a escolha, mas não esperam um pelo outro.
///
/// [autoPrintReceipt] vem do cadastro do restaurante: desligado, o recibo não
/// sai sozinho (o botão "Imprimir recibo" continua valendo). A NFC-e não
/// depende dele — ela é obrigação fiscal, não preferência da loja.
void startPaidOrderFollowUps({
  required void Function() showNextSale,
  required Future<String?> Function() choosePrinter,
  required Future<void> Function(Future<String?> printer) printReceipt,
  required Future<void> Function(Future<String?> printer) emitInvoice,
  required Future<void> Function() refreshCatalog,
  bool autoPrintReceipt = true,
}) {
  showNextSale();
  final printer = choosePrinter();
  if (autoPrintReceipt) unawaited(printReceipt(printer));
  unawaited(emitInvoice(printer));
  unawaited(refreshCatalog());
}
