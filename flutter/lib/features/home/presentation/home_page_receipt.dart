// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Recibo do cliente: pelo servidor quando dá, montado aqui quando não dá.
///
/// A autorização por senha de caixa mora junto porque é ela que libera a
/// reimpressão e as operações de gaveta — o mesmo diálogo, o mesmo caminho.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _ReceiptSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;

  Map<String, dynamic>? get activeOrder;
  Map<String, dynamic>? get selectedTable;
  Map<String, dynamic>? get selectedCommand;
  Map<String, dynamic>? get selectedCustomer;
  Map<String, dynamic>? get selectedRestaurant;
  Map<String, dynamic>? get cashSession;
  List<Map<String, dynamic>> get orderItems;
  List<Map<String, dynamic>> get registeredPayments;
  bool get printingReceipt;
  set printingReceipt(bool value);
  bool get isSecondaryStation;

  /// Imprime a NOTA COMPLETA DO CLIENTE (receipt: itens + valores + total) do
  /// pedido atual, a qualquer momento — sem finalizar/enviar à cozinha.
  Future<void> _printCustomerReceipt([
    Map<String, dynamic>? selectedOrder,
  ]) async {
    final order = selectedOrder ?? activeOrder;
    if (order == null || printingReceipt) return;
    setState(() => printingReceipt = true);
    try {
      final printers = await _list(
        '/printers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      );
      if (!mounted) return;
      if (printers.isEmpty) {
        _error(
          const ApiException(
            'Nenhuma impressora ativa foi cadastrada para este restaurante.',
          ),
        );
        return;
      }
      final master = widget.preferences.masterPrinterId;
      final hasMaster = printers.any((p) => '${p['id']}' == master);
      final printerId = hasMaster
          ? master
          : await showDialog<String>(
              context: context,
              builder: (_) => PrinterSelectionDialog(
                printers: printers,
                title: 'Imprimir recibo de venda',
                summary:
                    'Pedido #${order['sequence']} · ${_money(order['total'])}',
                description:
                    'A nota contém restaurante, cliente ou mesa, itens, observações, pagamentos e totais.',
              ),
            );
      if (printerId == null) return;
      final chosen = printers.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == printerId,
        orElse: () => null,
      );
      // A impressora é deste terminal, e o cupom sabe ser montado aqui: um
      // Caixa Secundário não precisa do Principal nem do backend para
      // entregar um recibo ao cliente. Pedir o cupom renderizado ao servidor
      // é conveniência (layout de referência e registro do trabalho), não
      // requisito — e num secundário essa rota nem existe, o que antes fazia
      // o botão não produzir absolutamente nada.
      if (chosen != null && isSecondaryStation) {
        await _printingStep(
          () => _printReceiptLocally(order, chosen),
          title: 'O recibo não saiu na impressora',
        );
        return;
      }
      try {
        final printJob = await api.post(
          '/orders/${order['id']}/print/',
          body: {
            'job_type': 'receipt',
            'printer': printerId,
            'manual_only': true,
          },
          accessToken: token,
        );
        final printer = printJob['printer'] as Map<String, dynamic>? ?? chosen;
        if (printer == null) {
          _error(
            const ApiException('A impressora selecionada não foi encontrada.'),
          );
          return;
        }
        await _printingStep(
          () => deviceAgent.printJobManually(printJob, printer),
          title: 'O recibo não saiu na impressora',
        );
      } on ApiException catch (error) {
        // Sem `PrintJob` do servidor o cliente continua com a mão estendida
        // esperando o comprovante. Qualquer recusa serve de gatilho — falta
        // de rede, servidor fora, ou uma rota que este terminal não alcança.
        if (chosen == null) rethrow;
        AppLogger.instance.info(
          'recibo_montado_localmente',
          data: {'motivo': error.message},
        );
        await _printingStep(
          () => _printReceiptLocally(order, chosen),
          title: 'O recibo não saiu na impressora',
        );
      }
    } catch (error) {
      // Sem isto o erro virava exceção assíncrona sem dono: o operador
      // apertava "imprimir recibo" e não acontecia nada, nem papel nem aviso.
      if (mounted) {
        _error(
          error,
          title: 'O recibo não pôde ser impresso',
          action: 'Confira a impressora selecionada e tente novamente.',
        );
      }
    } finally {
      if (mounted) setState(() => printingReceipt = false);
    }
  }

  /// Monta o recibo neste terminal e manda para a fila local.
  ///
  /// Mesmo layout do servidor ([LocalPrintRenderer]), mesma impressora. Pela
  /// fila: se faltar papel agora, o cupom sai sozinho quando ela voltar em vez
  /// de se perder.
  Future<bool> _printReceiptLocally(
    Map<String, dynamic> order,
    Map<String, dynamic> printer,
  ) async {
    final receiptPrinter = ReceiptPrinter(
      PrinterDevice.fromJson(printer),
      runtime: deviceAgent.printing,
    );
    final result = await deviceAgent.submit(
      receiptPrinter,
      receiptPrinter.compose(
        content: await _localReceiptText(order),
        barcode: LocalPrintRenderer.commandBarcode(order, selectedCommand),
      ),
    );
    // Quem pediu o recibo está olhando a impressora: o silêncio faria o
    // operador achar que o papel vem e mandar o cliente embora.
    if (!result.printed && mounted) {
      showAppToast(
        context,
        result.accepted
            ? 'A impressora não respondeu agora. O recibo está na fila e '
                  'sai assim que ela voltar.'
            : 'O recibo não pôde ser impresso. Confira a configuração '
                  'da impressora.',
        severity: AppErrorSeverity.warning,
      );
    }
    return true;
  }

  Future<String> _localReceiptText(Map<String, dynamic> order) async {
    final orderId = '${order['id']}';
    final store = api.localStore;
    final payments = store == null
        ? registeredPayments
        : await store.orders.payments(orderId);
    return LocalPrintRenderer.customerReceipt(
      order: order,
      restaurant: selectedRestaurant,
      payments: payments,
      table: selectedTable,
      command: selectedCommand,
      customer: selectedCustomer,
      operatorName: widget.controller.session?.user.name ?? '',
    );
  }
}
