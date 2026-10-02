part of 'printer.dart';

/// Um tipo de cupom por classe.
///
/// Elas nao reimplementam nada do envio, que e todo de [Printer]: so declaram
/// o que aquele cupom e — o `job_type` gravado na fila — e se ele pode esperar
/// na fila local. Antes essa distincao estava espalhada em cada tela, e era
/// por isso que o recibo de venda tinha um caminho de erro e a comanda
/// automatica tinha outro.

/// Recibo de venda / cupom do cliente.
class ReceiptPrinter extends Printer {
  ReceiptPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.receipt;
}

/// Comanda de produção (cozinha, bar, chapa).
class KitchenPrinter extends Printer {
  KitchenPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.kitchen;
}

/// Aviso de cancelamento de item já enviado à produção.
class KitchenCancelPrinter extends Printer {
  KitchenCancelPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.kitchenCancel;
}

/// Nota de pesagem da balança.
class WeighTicketPrinter extends Printer {
  WeighTicketPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.weighTicket;
}

/// DANFE NFC-e (o único com QR Code).
class FiscalDanfePrinter extends Printer {
  FiscalDanfePrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.fiscalDanfe;
}

/// Nota de teste do cadastro de impressoras.
class TestPrinter extends Printer {
  TestPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.printerTest;

  /// Um teste que sai meia hora depois não diz nada sobre o equipamento:
  /// quem clicou "testar" está olhando a impressora agora.
  @override
  bool get queueable => false;
}

/// Etiqueta da comanda, impressa em lote ("da 10 à 100").
class CommandLabelPrinter extends Printer {
  CommandLabelPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.commandLabel;

  /// O lote para onde a impressora falhou e diz o número: sessenta etiquetas
  /// saindo sozinhas meia hora depois, da fila, surpreenderiam o salão.
  @override
  bool get queueable => false;
}

/// Tipo de cupom que este PDV ainda não conhece.
class GenericPrinter extends Printer {
  GenericPrinter(super.device, {super.runtime, PrintJobType? type})
    : _type = type ?? PrintJobType.other;

  final PrintJobType _type;

  @override
  PrintJobType get jobType => _type;
}
