import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Uma mesa na lista de escolha, com o estado dela e quantos cartões já estão
/// sentados ali.
///
/// A contagem aparece porque é o que decide o gesto seguinte: uma mesa que já
/// tem quatro cartões vai recusar o quinto no servidor, e ver isso antes de
/// tocar evita a viagem.
class TableChoiceTile extends StatelessWidget {
  const TableChoiceTile({
    super.key,
    required this.table,
    required this.selected,
    required this.onTap,
  });

  final Map<String, dynamic> table;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final commands = (table['active_commands'] as List? ?? const []).length;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: AppTheme.radius,
        onTap: onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 120),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: selected
                ? scheme.primaryContainer
                : scheme.surfaceContainerLow,
            border: Border.all(
              color: selected ? scheme.primary : scheme.outlineVariant,
            ),
            borderRadius: AppTheme.radius,
          ),
          child: Row(
            children: [
              Icon(
                selected
                    ? Icons.check_box_outlined
                    : Icons.table_restaurant_outlined,
                color: selected ? scheme.primary : scheme.onSurfaceVariant,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Mesa ${table['number']}',
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      [
                        _estado(table['status']),
                        if (commands > 0)
                          '$commands ${commands == 1 ? 'comanda vinculada' : 'comandas vinculadas'}',
                      ].join(' · '),
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
  }

  static String _estado(dynamic status) => switch ('$status') {
    'occupied' => 'Ocupada',
    'reserved' => 'Reservada',
    _ => 'Livre',
  };
}
