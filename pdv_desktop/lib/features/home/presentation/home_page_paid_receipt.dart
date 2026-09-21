// Este mixin é consumido pela tela no mesmo library via `part`; o analisador
// não reconhece a referência ao método declarado em outro mixin.
// ignore_for_file: unused_element

part of 'home_page.dart';

/// Escolhe uma impressora uma vez para os dois documentos da venda paga.
mixin _PaidReceiptSection on _HomePageShared {
  LocalDeviceAgent get deviceAgent;

  Future<String?> _chooseSalePrinter(Map<String, dynamic> order) async {
    final saleRestaurantId = restaurantId;
    final masterId = widget.preferences.masterPrinterId;
    try {
      final printers = await _list(
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

  Future<void> _printSaleReceipt(
    Map<String, dynamic> order,
    Future<String?> printerChoice,
  ) async {
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
      await deviceAgent.printJobManually(printJob, printer);
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
