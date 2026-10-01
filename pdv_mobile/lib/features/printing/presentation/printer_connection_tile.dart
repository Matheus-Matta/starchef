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

  Future<void> _testConnection() async {
    setState(() => _testing = true);
    String message;
    try {
      await widget.agent.testPrinterConnection(widget.printer);
      message = 'Conectou em ${widget.printer.host}:${widget.printer.port}. '
          'Nenhum papel foi impresso.';
    } catch (error) {
      message = '$error';
    } finally {
      if (mounted) setState(() => _testing = false);
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
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
            Align(
              alignment: Alignment.centerRight,
              child: Padding(
                padding: const EdgeInsets.only(right: 12, bottom: 8),
                child: OutlinedButton.icon(
                  onPressed: !printer.supportsMobile || _testing
                      ? null
                      : _testConnection,
                  icon: _testing
                      ? const SizedBox.square(
                          dimension: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.wifi_find),
                  label: Text(_testing ? 'Testando...' : 'Testar conexão'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
