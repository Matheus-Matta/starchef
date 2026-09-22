import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_dialog.dart';
import 'table_choice_tile.dart';

typedef JsonMap = Map<String, dynamic>;

bool commandNeedsTableSelection(JsonMap command) {
  final tableId = command['current_table'];
  return tableId == null || '$tableId'.trim().isEmpty;
}

/// Resultado explícito da escolha de mesa.
///
/// [table] nulo significa SEM MESA — seguir sem vínculo, quando o cartão
/// ainda não tem mesa, ou tirá-lo da mesa em que está. Fechar o diálogo
/// devolve `null` e não muda nada.
class CommandTableSelection {
  const CommandTableSelection({this.table});

  final JsonMap? table;
}

class CommandTableSelectionDialog extends StatefulWidget {
  const CommandTableSelectionDialog({
    super.key,
    required this.command,
    required this.tables,
  });

  final JsonMap command;
  final List<JsonMap> tables;

  @override
  State<CommandTableSelectionDialog> createState() =>
      _CommandTableSelectionDialogState();
}

class _CommandTableSelectionDialogState
    extends State<CommandTableSelectionDialog> {
  JsonMap? selectedTable;

  /// O cartão já está sentado em alguma mesa?
  ///
  /// O mesmo diálogo serve aos dois momentos — antes de abrir o pedido, e
  /// depois, no detalhe do cartão. Só o texto muda: quem já tem mesa está
  /// MUDANDO de mesa, e "Sem mesa" deixa de ser "seguir assim" para virar
  /// "tirar da mesa".
  String get _mesaAtual =>
      '${widget.command['current_table_number'] ?? ''}'.trim();
  bool get _jaSentada => _mesaAtual.isNotEmpty;

  List<JsonMap> get linkableTables => widget.tables
      .where(
        (table) => table['is_active'] != false && table['status'] != 'cleaning',
      )
      .toList();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final available = linkableTables;
    return AppDialog(
      maxWidth: 620,
      title: Row(
        children: [
          Icon(Icons.qr_code_2_outlined, color: scheme.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _jaSentada
                  ? 'Comanda ${widget.command['number']} · Mesa $_mesaAtual'
                  : 'Comanda ${widget.command['number']} sem mesa',
            ),
          ),
        ],
      ),
      content: SizedBox(
        width: 560,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              _jaSentada
                  ? 'Escolha outra mesa para mudar o cartão de lugar, ou '
                        'tire-o da mesa em que está.'
                  : 'Esta comanda ainda não está vinculada. Selecione uma '
                        'mesa agora ou continue sem mesa para abrir o pedido.',
            ),
            const SizedBox(height: 14),
            if (available.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: scheme.surfaceContainerLow,
                  border: Border.all(color: scheme.outlineVariant),
                  borderRadius: AppTheme.radius,
                ),
                child: const Text(
                  'Nenhuma mesa disponível para vínculo neste momento.',
                ),
              )
            else
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 340),
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: available.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 6),
                  itemBuilder: (context, index) {
                    final table = available[index];
                    return TableChoiceTile(
                      table: table,
                      selected: '${selectedTable?['id']}' == '${table['id']}',
                      onTap: () => setState(() => selectedTable = table),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
      actions: [
        OutlinedButton(
          onPressed: () =>
              Navigator.pop(context, const CommandTableSelection()),
          child: Text(_jaSentada ? 'Tirar da mesa' : 'Sem mesa'),
        ),
        FilledButton.icon(
          onPressed: selectedTable == null
              ? null
              : () => Navigator.pop(
                  context,
                  CommandTableSelection(table: selectedTable),
                ),
          icon: const Icon(Icons.link),
          label: const Text('Vincular'),
        ),
      ],
    );
  }
}
