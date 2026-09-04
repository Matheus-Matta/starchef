import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/paginated_picker.dart';
import '../data/orders_repository.dart';

/// Escolha da comanda para abrir (ou retomar) um pedido.
///
/// Comanda ocupada aparece e é selecionável de propósito: é assim que o garçom
/// volta a uma mesa que já está sendo atendida para lançar mais itens — o
/// backend devolve o pedido em aberto em vez de criar outro.
Future<Map<String, dynamic>?> showCommandPicker(
  BuildContext context,
  OrdersRepository repository,
) => showModalBottomSheet<Map<String, dynamic>>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => SizedBox(
    height: MediaQuery.of(context).size.height * .85,
    child: Column(
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 0, 20, 12),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text(
              'Escolha a comanda',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
            ),
          ),
        ),
        Expanded(
          child: PaginatedPicker(
            searchHint: 'Número ou código da comanda',
            emptyMessage: 'Nenhuma comanda cadastrada neste restaurante.',
            fetch: (page, search) async {
              final result = await repository.commands(
                page: page,
                search: search,
              );
              return (rows: result.rows, hasMore: result.hasMore);
            },
            itemBuilder: (context, command) => _CommandTile(
              command: command,
              onTap: () => Navigator.of(context).pop(command),
            ),
          ),
        ),
      ],
    ),
  ),
);

class _CommandTile extends StatelessWidget {
  const _CommandTile({required this.command, required this.onTap});

  final Map<String, dynamic> command;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ocupada = command['status'] == 'occupied';
    final mesa = '${command['current_table_number'] ?? ''}'.trim();
    final cliente = '${command['customer_name'] ?? ''}'.trim();

    final detalhes = [
      if (ocupada) 'em atendimento',
      if (mesa.isNotEmpty && mesa != 'null') 'mesa $mesa',
      if (cliente.isNotEmpty && cliente != 'null') cliente,
    ];

    return PickerTile(
      title: 'Comanda ${command['number'] ?? ''}',
      subtitle: detalhes.isEmpty ? 'livre' : detalhes.join(' · '),
      onTap: onTap,
      leading: Container(
        height: 38,
        width: 38,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: (ocupada ? AppColors.warning : AppColors.success).withValues(
            alpha: .12,
          ),
          borderRadius: AppTheme.radius,
        ),
        child: Icon(
          ocupada ? Icons.pending_actions : Icons.check_circle_outline,
          size: 20,
          color: ocupada ? AppColors.warning : AppColors.success,
        ),
      ),
      trailing: Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
    );
  }
}
