// Este mixin é consumido pela tela no mesmo library via `part`; o analisador
// não reconhece a referência ao método declarado em outro mixin.
// ignore_for_file: unused_element

part of 'home_page.dart';

/// Escolhe uma impressora uma vez para os dois documentos da venda paga.
mixin _PaidReceiptSection on _HomePageShared {
  LocalDeviceAgent get deviceAgent;
  PdvRepository get repository;
  Map<String, dynamic>? get activeOrder;
  List<Map<String, dynamic>> get registeredPayments;
  Map<String, dynamic>? get selectedCustomer;
  Map<String, dynamic>? get selectedRestaurant;
  void _resetToNewSale();
  Future<void> _load();
  Future<bool> _decidirDanfe(
    Map<String, dynamic> order,
    Future<String?> salePrinter,
  );
  Future<void> _emitFiscalInvoice(
    Map<String, dynamic> order, {
    bool silentIfUnconfigured,
    bool automatic,
    Map<String, dynamic>? customer,
    Future<String?>? salePrinter,
    Future<bool>? danfe,
  });

  /// A venda está paga: libera a tela e dispara o resto em segundo plano —
  /// recibo, "Imprimir a NFC-e?" e a nota (`paid_order_follow_ups.dart`).
  ///
  /// Movido de `_PaymentSection`, que segue conferindo o recebimento.
  void _seguirDepoisDePago() {
    final paidOrder = Map<String, dynamic>.from(activeOrder!);
    // Lido AGORA, antes de `showNextSale` limpar a tela para a próxima venda:
    // depois dali `registeredPayments` está vazia, e o recibo sairia sem a
    // gaveta justamente na venda que a justifica.
    final paidInCash = registeredPayments.any(_PaymentSection._isCashPayment);
    final customer = selectedCustomer == null
        ? null
        : Map<String, dynamic>.from(selectedCustomer!);
    startPaidOrderFollowUps(
      showNextSale: _resetToNewSale,
      choosePrinter: () => _chooseSalePrinter(paidOrder),
      printReceipt: (printer) =>
          _printSaleReceipt(paidOrder, printer, paidInCash: paidInCash),
      // "Imprimir a NFC-e?" sai já, com a próxima venda liberada; a nota
      // segue em segundo plano levando a resposta (`paid_order_follow_ups`).
      askDanfe: selectedRestaurant?['ask_print_danfe'] == true
          ? (printer) => _decidirDanfe(paidOrder, printer)
          : null,
      emitInvoice: (printer, danfe) => _emitFiscalInvoice(
        paidOrder,
        customer: customer,
        salePrinter: printer,
        danfe: danfe,
        silentIfUnconfigured: true,
        automatic: true,
      ),
      refreshCatalog: _load,
      autoPrintReceipt: selectedRestaurant?['auto_print_receipt'] != false,
    );
  }

  Future<String?> _chooseSalePrinter(Map<String, dynamic> order) async {
    final saleRestaurantId = restaurantId;
    final masterId = widget.preferences.masterPrinterId;
    try {
      final printers = await repository.listCached(
        '/printers/',
        query: {
          'restaurant': saleRestaurantId,
          'is_active': true,
          'page_size': 100,
        },
      );
      if (!mounted) return null;
      if (printers.isEmpty) {
        throw const ApiException(
          'Nenhuma impressora ativa foi cadastrada para este restaurante.',
        );
      }
      final hasMaster = printers.any((p) => '${p['id']}' == masterId);
      if (hasMaster) return masterId;
      // `await` aqui dentro do `try`, e não só `return`: sem ele o `Future`
      // sai do bloco antes de completar, e uma falha do diálogo passa POR
      // FORA do `catch` abaixo — que é o que transforma qualquer tropeço em
      // "pagamento registrado, mas impressão pendente". Sem isso, o erro
      // chegaria cru a quem chamou, depois de o pagamento já ter sido gravado.
      return await showDialog<String>(
        context: context,
        builder: (_) => PrinterSelectionDialog(
          printers: printers,
          title: 'Imprimir recibo e DANFE NFC-e',
          summary: 'Pedido #${order['sequence']} · ${_money(order['total'])}',
          description:
              'A impressora escolhida receberá o recibo e, após a autorização da SEFAZ, o DANFE da NFC-e.',
        ),
      );
    } catch (error) {
      if (mounted) {
        _error(error, title: 'Pagamento registrado, mas impressão pendente');
      }
      return null;
    }
  }

  /// Imprime o recibo da venda paga.
  ///
  /// [paidInCash] decide a gaveta, e vem de quem registrou os recebimentos —
  /// aqui já não dá para saber: `order` é a cópia do pedido, não a lista de
  /// formas de pagamento. A gaveta sai NESTE trabalho, junto do recibo, e
  /// não numa segunda conexão com a mesma impressora.
  Future<void> _printSaleReceipt(
    Map<String, dynamic> order,
    Future<String?> printerChoice, {
    bool paidInCash = false,
  }) async {
    try {
      final printerId = await printerChoice;
      if (!mounted || printerId == null) return;
      final printJob = await api.post(
        '/orders/${order['id']}/print/',
        body: {
          'job_type': 'receipt',
          'printer': printerId,
          'manual_only': true,
        },
        accessToken: token,
      );
      if (!mounted) return;
      final printer = printJob['printer'] as Map<String, dynamic>?;
      if (printer == null) {
        throw const ApiException(
          'O trabalho de impressão voltou sem impressora.',
        );
      }
      await deviceAgent.printJobManually(
        printJob,
        printer,
        openCashDrawer: paidInCash,
      );
    } catch (error) {
      if (mounted) {
        _error(
          error,
          title: 'O pagamento foi registrado, mas o recibo não saiu',
          action: 'Confira a impressora e reimprima pela tela de Pedidos.',
        );
      }
    }
  }
}
