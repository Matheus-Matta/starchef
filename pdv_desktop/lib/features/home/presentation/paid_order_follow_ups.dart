import 'dart:async';

/// Libera o caixa antes de escolher a impressora e iniciar os efeitos da venda.
/// Recibo e NFC-e compartilham a escolha, mas não esperam um pelo outro.
void startPaidOrderFollowUps({
  required void Function() showNextSale,
  required Future<String?> Function() choosePrinter,
  required Future<void> Function(Future<String?> printer) printReceipt,
  required Future<void> Function(Future<String?> printer) emitInvoice,
  required Future<void> Function() refreshCatalog,
}) {
  showNextSale();
  final printer = choosePrinter();
  unawaited(printReceipt(printer));
  unawaited(emitInvoice(printer));
  unawaited(refreshCatalog());
}
