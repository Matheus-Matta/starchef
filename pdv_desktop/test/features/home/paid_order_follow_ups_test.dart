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
        emitInvoice: (printer, _) async {
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
        emitInvoice: (printer, _) async {
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

  test(
    'a pergunta do DANFE sai junto com a venda e a NFC-e não espera a resposta',
    () async {
      // A pergunta só aparecia DEPOIS de o servidor responder a emissão — que
      // podia levar a SEFAZ inteira, ou falhar. O caixa ficava esperando um
      // modal para liberar a próxima venda. Agora pergunta na hora, e a
      // emissão segue em segundo plano levando a resposta para quando a nota
      // puder ser impressa.
      final resposta = Completer<bool>();
      final events = <String>[];
      Future<bool>? recebida;

      startPaidOrderFollowUps(
        showNextSale: () => events.add('nova venda'),
        choosePrinter: () async => 'printer-1',
        printReceipt: (_) async {},
        askDanfe: (printer) {
          events.add('pergunta');
          return resposta.future;
        },
        emitInvoice: (printer, danfe) async {
          events.add('nfce');
          recebida = danfe;
        },
        refreshCatalog: () async {},
      );

      expect(events, ['nova venda', 'pergunta', 'nfce']);
      expect(resposta.isCompleted, isFalse);
      expect(identical(recebida, resposta.future), isTrue);
    },
  );
}
