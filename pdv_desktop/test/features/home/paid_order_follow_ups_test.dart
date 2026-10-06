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

  test(
    'restaurante com recibo automático desligado não imprime, mas emite a NFC-e',
    () async {
      // O restaurante desligou o recibo no painel. O PDV imprimia assim mesmo:
      // `printReceipt` era chamado sem condição nenhuma.
      final events = <String>[];
      final invoiceDone = Completer<void>();

      startPaidOrderFollowUps(
        showNextSale: () => events.add('nova venda'),
        choosePrinter: () async => 'printer-1',
        printReceipt: (_) async => events.add('recibo'),
        emitInvoice: (printer) async {
          events.add('danfe na ${await printer}');
          invoiceDone.complete();
        },
        refreshCatalog: () async {},
        autoPrintReceipt: false,
      );

      await invoiceDone.future;
      expect(events, ['nova venda', 'danfe na printer-1']);
    },
  );
}
