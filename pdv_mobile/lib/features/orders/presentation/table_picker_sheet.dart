import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/shadcn_layout.dart';

/// Pergunta em qual mesa o cliente sentou, depois de abrir a comanda.
///
/// É opcional e vem DEPOIS do pedido existir: a comanda anda com o cliente
/// (ele pode chegar em pé, sentar depois, trocar de mesa), então o vínculo com
/// a mesa é um detalhe do atendimento — não a forma de abrir o pedido.
Future<Map<String, dynamic>?> showTablePicker(
  BuildContext context,
  List<Map<String, dynamic>> tables, {
  required String commandLabel,
}) => showAppSheet<Map<String, dynamic>>(
  context,
  builder: (context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      AppSheetHeader(
        title: 'Vincular a uma mesa?',
        subtitle: '$commandLabel aberta. Se o cliente sentou, escolha a mesa.',
      ),
      Flexible(
        child: tables.isEmpty
            ? const AppEmptyState(
                icon: Icons.table_restaurant_outlined,
                title: 'Nenhuma mesa ativa',
                description:
                    'Este restaurante não tem mesas cadastradas e ativas.',
              )
            : _TableGrid(tables: tables),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
        child: ShadButton.ghost(
          onPressed: () => Navigator.of(context).pop(),
          height: AppTheme.controlHeight,
          child: const Text('Agora não'),
        ),
      ),
    ],
  ),
);

class _TableGrid extends StatelessWidget {
  const _TableGrid({required this.tables});

  final List<Map<String, dynamic>> tables;

  @override
  Widget build(BuildContext context) => GridView.builder(
    padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
    shrinkWrap: true,
    gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
      maxCrossAxisExtent: 120,
      mainAxisSpacing: AppTheme.gap,
      crossAxisSpacing: AppTheme.gap,
      childAspectRatio: 1.35,
    ),
    itemCount: tables.length,
    itemBuilder: (context, index) {
      final table = tables[index];
      return ShadButton.outline(
        onPressed: () => Navigator.of(context).pop(table),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'Mesa ${table['number']}',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            // Mesa ocupada continua escolhível: é assim que duas comandas
            // dividem a mesma mesa.
            if (table['status'] == 'occupied')
              const Text('ocupada', style: TextStyle(fontSize: 11)),
          ],
        ),
      );
    },
  );
}
