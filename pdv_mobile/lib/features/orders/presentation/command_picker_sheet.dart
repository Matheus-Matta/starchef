import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/paginated_picker.dart';
import '../../../core/widgets/picker_tile.dart';
import '../data/orders_repository.dart';
import 'order_formatters.dart';

/// Escolha da comanda para abrir (ou retomar) um pedido.
///
/// Comanda ocupada aparece e é selecionável de propósito: é assim que o garçom
/// volta a uma mesa que já está sendo atendida para lançar mais itens — o
/// backend devolve o pedido em aberto em vez de criar outro.
Future<Map<String, dynamic>?> showCommandPicker(
  BuildContext context,
  OrdersRepository repository,
) => showAppSheet<Map<String, dynamic>>(
  context,
  heightFactor: .85,
  builder: (context) => Column(
    children: [
      const AppSheetHeader(title: 'Escolha a comanda'),
      Expanded(
        child: PaginatedPicker(
          searchHint: 'Número ou código da comanda',
          emptyMessage: 'Nenhuma comanda cadastrada neste restaurante.',
          fetch: (page, search) =>
              repository.commands(page: page, search: search),
          itemBuilder: (context, command) => _CommandTile(
            command: command,
            onTap: () => Navigator.of(context).pop(command),
          ),
        ),
      ),
    ],
  ),
);

class _CommandTile extends StatelessWidget {
  const _CommandTile({required this.command, required this.onTap});

  final Map<String, dynamic> command;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final busy = command['status'] == 'occupied';
    // O caixa está montando uma conta agrupada com esta comanda AGORA. Abrir
    // o pedido dela devolve 409, e a lista precisa dizer isso antes do toque:
    // um item lançado aqui ficaria fora do pagamento que o caixa está lendo em
    // voz alta para o cliente.
    final closing = fieldText(command['closing_merge']).isNotEmpty;
    final table = fieldText(command['current_table_number']);
    final customer = fieldText(command['customer_name']);
    final details = [
      if (closing) 'em fechamento no caixa' else if (busy) 'em atendimento',
      if (table.isNotEmpty) 'mesa $table',
      if (customer.isNotEmpty) customer,
    ];
    final color = closing
        ? AppColors.danger
        : (busy ? AppColors.warning : AppColors.success);

    return PickerTile(
      title: 'Comanda ${command['number'] ?? ''}',
      subtitle: details.isEmpty ? 'livre' : details.join(' · '),
      onTap: onTap,
      // `enabled: false` apaga o cartão e tira o toque: a comanda continua
      // VISÍVEL (o garçom precisa saber que ela existe e por que não dá para
      // usá-la), mas não é escolhível.
      enabled: !closing,
      leading: Container(
        height: 38,
        width: 38,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: color.withValues(alpha: .12),
          borderRadius: AppTheme.radius,
        ),
        child: Icon(
          closing
              ? Icons.point_of_sale_outlined
              : (busy ? Icons.pending_actions : Icons.check_circle_outline),
          size: 20,
          color: color,
        ),
      ),
      trailing: Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
    );
  }
}
