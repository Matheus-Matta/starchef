import 'package:flutter/material.dart';

/// Seletor reutilizável para operações de impressão manual.
class PrinterSelectionDialog extends StatefulWidget {
  const PrinterSelectionDialog({
    super.key,
    required this.printers,
    required this.title,
    required this.summary,
    required this.description,
  });

  final List<Map<String, dynamic>> printers;
  final String title;
  final String summary;
  final String description;

  @override
  State<PrinterSelectionDialog> createState() => _PrinterSelectionDialogState();
}

class _PrinterSelectionDialogState extends State<PrinterSelectionDialog> {
  late String selectedId = '${widget.printers.first['id']}';

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          const Icon(Icons.receipt_long_outlined),
          const SizedBox(width: 10),
          Expanded(child: Text(widget.title)),
        ],
      ),
      content: SizedBox(
        width: 440,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.summary,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 18),
            DropdownButtonFormField<String>(
              initialValue: selectedId,
              isExpanded: true,
              decoration: const InputDecoration(
                labelText: 'Impressora',
                helperText: 'Selecione o equipamento que receberá a nota.',
                prefixIcon: Icon(Icons.print_outlined),
              ),
              items: widget.printers
                  .map(
                    (printer) => DropdownMenuItem(
                      value: '${printer['id']}',
                      child: Text(
                        '${printer['name']} · ${printer['connection_type'] ?? 'Windows'}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (value) {
                if (value != null) setState(() => selectedId = value);
              },
            ),
            const SizedBox(height: 12),
            Text(widget.description),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          onPressed: () => Navigator.pop(context, selectedId),
          icon: const Icon(Icons.print),
          label: const Text('Imprimir'),
        ),
      ],
    );
  }
}
