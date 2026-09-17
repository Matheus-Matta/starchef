import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

class TableDetailsPanel extends StatelessWidget {
  const TableDetailsPanel({
    super.key,
    required this.table,
    required this.onBack,
    required this.onOpenCommand,
  });

  final Map<String, dynamic> table;
  final VoidCallback onBack;
  final ValueChanged<Map<String, dynamic>> onOpenCommand;

  @override
  Widget build(BuildContext context) {
    final activeCommands = (table['active_commands'] as List? ?? const [])
        .cast<Map<String, dynamic>>();
    final occupied = activeCommands.isNotEmpty;
    final color = occupied ? Colors.orange : Colors.green;
    final scheme = Theme.of(context).colorScheme;

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1400),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextButton.icon(
                onPressed: onBack,
                icon: const Icon(Icons.arrow_back),
                label: const Text('Voltar para Mesas'),
              ),
              const SizedBox(height: 10),
              LayoutBuilder(
                builder: (context, constraints) {
                  final identity = Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Mesa ${table['number']}',
                        style: Theme.of(context).textTheme.headlineMedium
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      Text(
                        '${table['capacity'] ?? 0} lugares · ${table['sector_name'] ?? 'Sem setor'}',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(color: scheme.onSurfaceVariant),
                      ),
                    ],
                  );
                  final badge = ShadBadge.raw(
                    variant: ShadBadgeVariant.outline,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    backgroundColor: color.withValues(alpha: 0.1),
                    foregroundColor: color.shade800,
                    shape: RoundedRectangleBorder(
                      borderRadius: AppTheme.radius,
                      side: BorderSide(color: color.shade300),
                    ),
                    child: Text(
                      occupied ? 'Ocupada' : 'Disponível',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: color.shade800,
                      ),
                    ),
                  );
                  if (constraints.maxWidth < 520) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        identity,
                        const SizedBox(height: 10),
                        Align(alignment: Alignment.centerLeft, child: badge),
                      ],
                    );
                  }
                  return Row(
                    children: [
                      Expanded(child: identity),
                      const SizedBox(width: 16),
                      badge,
                    ],
                  );
                },
              ),
              const SizedBox(height: 22),
              Text(
                'Comandas Vinculadas (${activeCommands.length})',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: activeCommands.isEmpty
                    ? const AppEmptyState(
                        icon: Icons.link_off_outlined,
                        title: 'Nenhuma comanda vinculada',
                        description:
                            'Vincule uma comanda para acompanhar o atendimento desta mesa.',
                      )
                    : ListView.separated(
                        itemCount: activeCommands.length,
                        separatorBuilder: (_, _) => const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          final command = activeCommands[index];
                          return ShadCard(
                            padding: EdgeInsets.zero,
                            radius: AppTheme.radius,
                            shadows: const [],
                            columnCrossAxisAlignment:
                                CrossAxisAlignment.stretch,
                            child: Material(
                              type: MaterialType.transparency,
                              child: ListTile(
                                contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                  vertical: 8,
                                ),
                                leading: CircleAvatar(
                                  backgroundColor: scheme.primaryContainer,
                                  child: Text(
                                    '${command['number']}',
                                    style: TextStyle(
                                      color: scheme.onPrimaryContainer,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                ),
                                title: Text(
                                  command['customer_name']?.isNotEmpty == true
                                      ? command['customer_name']
                                      : 'Comanda ${command['number']}',
                                  style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                subtitle: Text(
                                  command['code'] ?? 'Sem código',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: scheme.onSurfaceVariant,
                                  ),
                                ),
                                onTap: () => onOpenCommand(command),
                                trailing: const Icon(Icons.chevron_right),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
