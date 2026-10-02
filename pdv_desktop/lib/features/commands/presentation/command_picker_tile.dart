import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';

/// Um cartão do "Selecione a comanda" da venda: número, livre/em uso e quem.
class CommandPickerTile extends StatelessWidget {
  const CommandPickerTile({
    super.key,
    required this.comanda,
    required this.onTap,
  });

  final Map<String, dynamic> comanda;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final ocupada =
        comanda['current_order_id'] != null || comanda['status'] == 'occupied';
    final cor = ocupada ? Colors.orange : Colors.green;
    final cliente = comanda['customer_name']?.toString().trim() ?? '';
    return ShadCard(
      padding: EdgeInsets.zero,
      radius: AppTheme.radius,
      shadows: const [],
      border: ShadBorder.all(color: cor.shade300),
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    '${comanda['number']}',
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const Spacer(),
                  Container(
                    width: 9,
                    height: 9,
                    decoration: BoxDecoration(
                      color: cor,
                      shape: BoxShape.circle,
                    ),
                  ),
                ],
              ),
              const Spacer(),
              Text(
                ocupada ? 'Em uso' : 'Livre',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: cor.shade800,
                ),
              ),
              Text(
                cliente.isNotEmpty ? cliente : '${comanda['code'] ?? '—'}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
