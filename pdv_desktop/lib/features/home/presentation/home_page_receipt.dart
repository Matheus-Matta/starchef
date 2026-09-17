// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Recibo do cliente.
///
/// Quem monta o documento é o servidor — ele é o dono do preço, do imposto e
/// do layout. Este terminal escolhe a impressora e põe no papel: é ele que
/// enxerga o equipamento do balcão. A fila local existe entre uma coisa e
/// outra, para o cupom não se perder quando falta papel.
///
/// A autorização por senha de caixa mora junto porque é ela que libera a
/// reimpressão e as operações de gaveta — o mesmo diálogo, o mesmo caminho.
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
}
