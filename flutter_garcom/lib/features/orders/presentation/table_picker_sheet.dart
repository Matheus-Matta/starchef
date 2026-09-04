import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';

/// Pergunta em qual mesa o cliente sentou, depois de abrir a comanda.
///
/// É opcional e vem DEPOIS do pedido existir: a comanda anda com o cliente
/// (ele pode chegar em pé, sentar depois, trocar de mesa), então o vínculo com
/// a mesa é um detalhe do atendimento — não a forma de abrir o pedido.
Future<Map<String, dynamic>?> showTablePicker(
  BuildContext context,
  List<Map<String, dynamic>> tables, {
  required String commandLabel,
}) => showModalBottomSheet<Map<String, dynamic>>(
  context: context,
  isScrollControlled: true,
  showDragHandle: true,
  builder: (context) => SafeArea(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  'Vincular a uma mesa?',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '$commandLabel aberta. Se o cliente sentou, escolha a mesa.',
                style: TextStyle(
                  fontSize: 13,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Flexible(
          child: tables.isEmpty
              ? const Padding(
                  padding: EdgeInsets.all(28),
                  child: Text('Nenhuma mesa ativa neste restaurante.'),
                )
              : GridView.builder(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
                  shrinkWrap: true,
                  gridDelegate:
                      const SliverGridDelegateWithMaxCrossAxisExtent(
                        maxCrossAxisExtent: 120,
                        mainAxisSpacing: 10,
                        crossAxisSpacing: 10,
                        childAspectRatio: 1.35,
                      ),
                  itemCount: tables.length,
                  itemBuilder: (context, index) {
                    final table = tables[index];
                    final ocupada = table['status'] == 'occupied';
                    return ShadButton.outline(
                      onPressed: () => Navigator.of(context).pop(table),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            'Mesa ${table['number']}',
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          if (ocupada)
                            const Text(
                              'ocupada',
                              style: TextStyle(fontSize: 11),
                            ),
                        ],
                      ),
                    );
                  },
                ),
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
  ),
);
