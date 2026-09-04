import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_dialog.dart';

typedef JsonMap = Map<String, dynamic>;

bool commandNeedsTableSelection(JsonMap command) {
  final tableId = command['current_table'];
  return tableId == null || '$tableId'.trim().isEmpty;
}

/// Resultado explícito do aviso exibido antes de abrir uma comanda sem mesa.
///
/// [table] nulo significa que o operador confirmou a abertura sem vínculo;
/// fechar o diálogo retorna `null` e cancela toda a abertura.
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
          Expanded(child: Text('Comanda ${widget.command['number']} sem mesa')),
        ],
      ),
      content: SizedBox(
        width: 560,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Esta comanda ainda não está vinculada. Selecione uma mesa '
              'agora ou continue sem mesa para abrir o pedido.',
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
                    final selected =
                        '${selectedTable?['id']}' == '${table['id']}';
                    final commands =
                        (table['active_commands'] as List? ?? const []).length;
                    return Material(
                      color: Colors.transparent,
                      child: InkWell(
                        borderRadius: AppTheme.radius,
                        onTap: () => setState(() => selectedTable = table),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 120),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 10,
                          ),
                          decoration: BoxDecoration(
                            color: selected
                                ? scheme.primaryContainer
                                : scheme.surfaceContainerLow,
                            border: Border.all(
                              color: selected
                                  ? scheme.primary
                                  : scheme.outlineVariant,
                            ),
                            borderRadius: AppTheme.radius,
                          ),
                          child: Row(
                            children: [
                              Icon(
                                selected
                                    ? Icons.check_box_outlined
                                    : Icons.table_restaurant_outlined,
                                color: selected
                                    ? scheme.primary
                                    : scheme.onSurfaceVariant,
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Mesa ${table['number']}',
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w800,
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      '${_statusLabel(table['status'])}'
                                      '${commands > 0 ? ' · $commands ${commands == 1 ? 'comanda vinculada' : 'comandas vinculadas'}' : ''}',
                                      style: TextStyle(
                                        color: scheme.onSurfaceVariant,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
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
          child: const Text('Sem mesa'),
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

  String _statusLabel(dynamic status) => switch ('$status') {
    'occupied' => 'Ocupada',
    'reserved' => 'Reservada',
    _ => 'Livre',
  };
}
