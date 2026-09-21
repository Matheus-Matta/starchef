import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/paid_order_follow_ups.dart';

void main() {
  test(
    'venda volta ao catálogo e compartilha a impressora escolhida',
    () async {
      // Evita dois modais e não espera a escolha para começar a emitir a NFC-e.
      final selectedPrinter = Completer<String?>();
      final receiptDone = Completer<void>();
      final invoiceDone = Completer<void>();
      final events = <String>[];

      startPaidOrderFollowUps(
        showNextSale: () => events.add('nova venda'),
        choosePrinter: () {
          events.add('seletor');
          return selectedPrinter.future;
        },
        printReceipt: (printer) async {
          events.add('recibo');
          events.add('recibo na ${await printer}');
          receiptDone.complete();
        },
        emitInvoice: (printer) async {
          events.add('nfce');
          events.add('danfe na ${await printer}');
          invoiceDone.complete();
        },
        refreshCatalog: () async => events.add('atualizar'),
      );

      expect(events, ['nova venda', 'seletor', 'recibo', 'nfce', 'atualizar']);
      expect(selectedPrinter.isCompleted, isFalse);
      selectedPrinter.complete('printer-1');
      await Future.wait([receiptDone.future, invoiceDone.future]);
      expect(events, [
        'nova venda',
        'seletor',
        'recibo',
        'nfce',
        'atualizar',
        'recibo na printer-1',
        'danfe na printer-1',
      ]);
    },
  );
}
