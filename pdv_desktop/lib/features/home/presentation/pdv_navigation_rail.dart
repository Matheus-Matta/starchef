import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import 'pdv_navigation_shell.dart';

/// Navegação fixa do posto de venda. A largura nunca muda: o catálogo não
/// salta quando o operador troca de tela e os cinco destinos permanecem no
/// mesmo lugar durante todo o turno.
class PdvNavigationRail extends StatelessWidget {
  const PdvNavigationRail({
    super.key,
    required this.selected,
    required this.onSelected,
    required this.showOrders,
    required this.showFinance,
  });

  final PdvDestination selected;
  final ValueChanged<PdvDestination> onSelected;
  final bool showOrders;
  final bool showFinance;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = <_RailEntry>[
      // "Venda", igual à barra lateral expandida: o destino é o mesmo, e o
      // trilho e a barra precisam chamá-lo pelo mesmo nome.
      const _RailEntry(PdvDestination.sale, 'Venda', Icons.grid_view_rounded),
      if (showOrders)
        const _RailEntry(
          PdvDestination.orders,
          'Pedidos',
          Icons.receipt_long_outlined,
        ),
      const _RailEntry(
        PdvDestination.tables,
        'Mesas',
        Icons.table_restaurant_outlined,
      ),
      const _RailEntry(
        PdvDestination.commands,
        'Comandas',
        Icons.qr_code_2_outlined,
      ),
      if (showFinance)
        const _RailEntry(
          PdvDestination.finance,
          'Caixa',
          Icons.account_balance_wallet_outlined,
        ),
      const _RailEntry(PdvDestination.scale, 'Balança', Icons.scale_outlined),
      const _RailEntry(PdvDestination.settings, 'Mais', Icons.apps_outlined),
    ];
    return Container(
      width: 72,
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(right: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Column(
        children: [
          SizedBox(
            height: 58,
            child: Center(
              child: Image.asset('assets/logoicon.png', width: 34, height: 34),
            ),
          ),
          Divider(height: 1, color: scheme.outlineVariant),
          const SizedBox(height: 8),
          for (final entry in entries)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
              child: _RailButton(
                entry: entry,
                selected: _isSelected(entry.destination),
                onTap: () => onSelected(entry.destination),
              ),
            ),
          const Spacer(),
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Tooltip(
              message: 'Ajuda e atalhos: F1',
              child: Text(
                'F1',
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  bool _isSelected(PdvDestination destination) => selected == destination;
}

class _RailButton extends StatelessWidget {
  const _RailButton({
    required this.entry,
    required this.selected,
    required this.onTap,
  });

  final _RailEntry entry;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final foreground = selected ? scheme.primary : scheme.onSurfaceVariant;
    return Tooltip(
      message: entry.label,
      waitDuration: const Duration(milliseconds: 350),
      child: Material(
        color: selected ? scheme.primaryContainer : Colors.transparent,
        borderRadius: AppTheme.radius,
        child: InkWell(
          onTap: onTap,
          borderRadius: AppTheme.radius,
          focusColor: scheme.primaryContainer,
          child: Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              border: selected
                  ? Border(left: BorderSide(color: scheme.primary, width: 3))
                  : null,
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(entry.icon, size: 21, color: foreground),
                const SizedBox(height: 3),
                Text(
                  entry.label,
                  maxLines: 1,
                  style: TextStyle(
                    color: foreground,
                    fontSize: 10,
                    fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RailEntry {
  const _RailEntry(this.destination, this.label, this.icon);

  final PdvDestination destination;
  final String label;
  final IconData icon;
}
