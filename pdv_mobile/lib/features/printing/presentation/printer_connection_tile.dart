import 'package:flutter/material.dart';

import '../domain/mobile_printer.dart';
import '../services/mobile_print_agent.dart';

class PrinterConnectionTile extends StatefulWidget {
  const PrinterConnectionTile({
    super.key,
    required this.printer,
    required this.agent,
  });

  final MobilePrinter printer;
  final MobilePrintAgent agent;

  @override
  State<PrinterConnectionTile> createState() => _PrinterConnectionTileState();
}

class _PrinterConnectionTileState extends State<PrinterConnectionTile> {
  bool _testing = false;

  Future<void> _testConnection() => _runTest(
    () => widget.agent.testPrinterConnection(widget.printer),
    connected: true,
  );

  Future<void> _printTestPage() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Imprimir teste?'),
        content: Text(
          'A impressora ${widget.printer.name} vai imprimir um recibo curto.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Imprimir'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _runTest(
      () => widget.agent.printTestPage(widget.printer),
      connected: false,
    );
  }

  Future<void> _runTest(
    Future<void> Function() action, {
    required bool connected,
  }) async {
    setState(() => _testing = true);
    String message;
    try {
      await action();
      message = connected
          ? 'Conexão TCP aberta em ${widget.printer.host}:${widget.printer.port}.'
          : 'Dados do teste enviados. Confira o papel e se o texto saiu legível.';
    } catch (error) {
      message = '$error';
    } finally {
      if (mounted) setState(() => _testing = false);
    }
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final printer = widget.printer;
    final subtitle = printer.acceptsAutomaticJobs
        ? '${printer.host}:${printer.port} • ${printer.isEscPos ? 'ESC/POS' : 'texto'}'
        : printer.supportsMobile
        ? 'Impressão automática desativada no backend'
        : 'Somente impressoras TCP/IP podem ser usadas no celular';
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          children: [
            ListTile(
              leading: Icon(
                printer.supportsMobile ? Icons.print_outlined : Icons.block,
              ),
              title: Text(printer.name),
              subtitle: Text(subtitle),
            ),
            Padding(
              padding: const EdgeInsets.only(right: 12, bottom: 8),
              child: Wrap(
                alignment: WrapAlignment.end,
                spacing: 8,
                children: [
                  OutlinedButton.icon(
                    onPressed: !printer.supportsMobile || _testing
                        ? null
                        : _testConnection,
                    icon: const Icon(Icons.wifi_find),
                    label: Text(_testing ? 'Testando...' : 'Testar conexão'),
                  ),
                  FilledButton.tonalIcon(
                    onPressed: !printer.supportsMobile || _testing
                        ? null
                        : _printTestPage,
                    icon: const Icon(Icons.print_outlined),
                    label: const Text('Imprimir teste'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
