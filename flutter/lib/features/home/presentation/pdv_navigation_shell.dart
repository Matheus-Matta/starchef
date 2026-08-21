import 'package:flutter/material.dart';

import '../../../core/network/api_client.dart';
import '../../devices/services/local_device_agent.dart';

/// Destinos da barra lateral.
///
/// Delivery não está aqui de propósito: ele deixou de ser um módulo próprio e
/// passou a existir apenas como tipo de pedido dentro do fluxo de Pedidos.
enum PdvDestination { menu, tables, orders, finance, scale, settings }

class PdvSidebar extends StatelessWidget {
  const PdvSidebar({
    super.key,
    required this.expanded,
    required this.selected,
    required this.onToggle,
    required this.onSelected,
    required this.userName,
    required this.restaurantName,
    required this.onLogout,
    this.showOrders = true,
    this.showScale = true,
    this.showSettings = true,
  });

  final bool expanded;
  final PdvDestination selected;
  final VoidCallback onToggle;
  final ValueChanged<PdvDestination> onSelected;
  final String userName;
  final String restaurantName;
  final VoidCallback onLogout;
  final bool showOrders;
  final bool showScale;
  final bool showSettings;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final destinations = <_SidebarEntry>[
      const _SidebarEntry(
        destination: PdvDestination.menu,
        label: 'Menu',
        icon: Icons.grid_view_rounded,
      ),
      const _SidebarEntry(
        destination: PdvDestination.tables,
        label: 'Mesas',
        icon: Icons.table_restaurant_outlined,
      ),
      if (showOrders)
        const _SidebarEntry(
          destination: PdvDestination.orders,
          label: 'Pedidos',
          icon: Icons.receipt_long_outlined,
        ),
      const _SidebarEntry(
        destination: PdvDestination.finance,
        label: 'Financeiro',
        icon: Icons.account_balance_wallet_outlined,
      ),
      if (showScale)
        const _SidebarEntry(
          destination: PdvDestination.scale,
          label: 'Balança rápida',
          icon: Icons.scale_outlined,
        ),
      if (showSettings)
        const _SidebarEntry(
          destination: PdvDestination.settings,
          label: 'Configurações',
          icon: Icons.settings_outlined,
        ),
    ];

    return SizedBox(
      width: expanded ? 224 : 76,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border(right: BorderSide(color: scheme.outlineVariant)),
        ),
        child: SafeArea(
          right: false,
          child: Column(
            children: [
              SizedBox(
                height: 76,
                child: Padding(
                  padding: EdgeInsets.symmetric(horizontal: expanded ? 18 : 14),
                  child: Row(
                    mainAxisAlignment: expanded
                        ? MainAxisAlignment.start
                        : MainAxisAlignment.center,
                    children: [
                      Container(
                        width: 42,
                        height: 42,
                        padding: const EdgeInsets.all(7),
                        decoration: BoxDecoration(
                          color: scheme.primaryContainer,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Image.asset(
                          'assets/logoicon.png',
                          filterQuality: FilterQuality.high,
                        ),
                      ),
                      if (expanded) ...[
                        const SizedBox(width: 11),
                        Expanded(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'STARCHEF',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: scheme.primary,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w900,
                                  letterSpacing: .8,
                                ),
                              ),
                              Text(
                                'Ponto de venda',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: scheme.onSurfaceVariant,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              Divider(height: 1, color: scheme.outlineVariant),
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 12, 10, 8),
                child: Align(
                  alignment: expanded
                      ? Alignment.centerRight
                      : Alignment.center,
                  child: IconButton(
                    tooltip: expanded ? 'Recolher menu' : 'Expandir menu',
                    onPressed: onToggle,
                    icon: Icon(
                      expanded
                          ? Icons.keyboard_double_arrow_left
                          : Icons.keyboard_double_arrow_right,
                    ),
                  ),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  itemCount: destinations.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 5),
                  itemBuilder: (context, index) {
                    final item = destinations[index];
                    return _DestinationButton(
                      entry: item,
                      expanded: expanded,
                      selected: selected == item.destination,
                      onTap: () => onSelected(item.destination),
                    );
                  },
                ),
              ),
              Divider(height: 1, color: scheme.outlineVariant),
              if (expanded)
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
                  child: Row(
                    children: [
                      CircleAvatar(
                        radius: 19,
                        backgroundColor: scheme.primaryContainer,
                        foregroundColor: scheme.onPrimaryContainer,
                        child: Text(
                          _initials(userName),
                          style: const TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              userName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 13,
                              ),
                            ),
                            Text(
                              restaurantName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: scheme.onSurfaceVariant,
                                fontSize: 10,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 4, 10, 12),
                child: _SidebarAction(
                  expanded: expanded,
                  label: 'Sair',
                  icon: Icons.logout,
                  onTap: onLogout,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _initials(String value) {
    final parts = value
        .trim()
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .take(2)
        .toList();
    if (parts.isEmpty) return 'SC';
    return parts.map((part) => part[0].toUpperCase()).join();
  }
}

class PdvConnectionBadge extends StatelessWidget {
  const PdvConnectionBadge({super.key, required this.status, this.onPressed});

  final NetworkSyncStatus status;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final offline = status.phase == NetworkSyncPhase.offline;
    final (label, icon, foreground, background) = switch (status.phase) {
      NetworkSyncPhase.unknown => (
        'Verificando',
        Icons.cloud_queue_outlined,
        scheme.onSurfaceVariant,
        scheme.surfaceContainer,
      ),
      NetworkSyncPhase.offline => (
        status.total > 0 ? 'Offline · ${status.total}' : 'Offline',
        Icons.cloud_off_outlined,
        scheme.error,
        scheme.errorContainer,
      ),
      NetworkSyncPhase.syncing => (
        status.total > 0 ? 'Sincronizando ${status.total}' : 'Sincronizando',
        Icons.sync_rounded,
        scheme.onTertiaryContainer,
        scheme.tertiaryContainer,
      ),
      NetworkSyncPhase.degraded => (
        status.retrying > 0 ? 'Instável · ${status.retrying}' : 'Instável',
        Icons.cloud_sync_outlined,
        const Color(0xFF9A5B00),
        const Color(0xFFFFF3D6),
      ),
      NetworkSyncPhase.blocked => (
        'Revisar ${status.blocked}',
        Icons.sync_problem_outlined,
        scheme.error,
        scheme.errorContainer,
      ),
      NetworkSyncPhase.online => (
        'Online',
        Icons.cloud_done_outlined,
        const Color(0xFF167A3E),
        const Color(0xFFE8F7EE),
      ),
    };

    final content = Container(
      height: 38,
      padding: const EdgeInsets.symmetric(horizontal: 11),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: foreground.withValues(alpha: .18)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 17, color: foreground),
          const SizedBox(width: 7),
          Text(
            label,
            style: TextStyle(
              color: foreground,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
    return Tooltip(
      message: offline
          ? 'Sem conexão. As operações compatíveis ficam na fila local.'
          : status.blocked > 0
          ? '${status.blocked} operação(ões) precisam de revisão.'
          : status.total > 0
          ? '${status.total} operação(ões) aguardando confirmação do servidor.'
          : status.lastError ??
                'Conectado ao servidor e sem operações pendentes.',
      child: onPressed == null
          ? content
          : InkWell(
              onTap: onPressed,
              borderRadius: BorderRadius.circular(10),
              child: content,
            ),
    );
  }
}

/// Estado do periférico de impressão acompanhado pelo agente local.
class PdvPrinterBadge extends StatelessWidget {
  const PdvPrinterBadge({
    super.key,
    required this.status,
    this.compact = false,
  });

  final PrinterAvailability status;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final available = status.phase == PrinterAvailabilityPhase.available;
    final checking = status.phase == PrinterAvailabilityPhase.checking;
    final foreground = checking
        ? scheme.onSurfaceVariant
        : available
        ? const Color(0xFF167A3E)
        : scheme.error;
    final background = checking
        ? scheme.surfaceContainer
        : available
        ? const Color(0xFFE8F7EE)
        : scheme.errorContainer;
    final icon = checking
        ? Icons.sync
        : available
        ? Icons.print_rounded
        : Icons.print_disabled_outlined;
    final content = Container(
      height: 38,
      padding: EdgeInsets.symmetric(horizontal: compact ? 10 : 11),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: foreground.withValues(alpha: .18)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 17, color: foreground),
          if (!compact) ...[
            const SizedBox(width: 7),
            Text(
              status.message,
              style: TextStyle(
                color: foreground,
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ],
      ),
    );
    return Tooltip(message: status.message, child: content);
  }
}

/// Estado da ligação deste caixa secundário com o Caixa Principal.
///
/// Fica visível o tempo todo porque, sem o principal, o secundário **não
/// grava**. Deixar isso aparecer só na hora do erro faria o operador montar um
/// pedido inteiro para descobrir no fim que não dava para lançar.
class PdvPrincipalBadge extends StatelessWidget {
  const PdvPrincipalBadge({
    super.key,
    required this.connected,
    required this.detail,
    this.onPressed,
    this.compact = false,
  });

  final bool connected;
  final String detail;
  final VoidCallback? onPressed;

  /// Só o ícone, para caber no cabeçalho estreito sem empurrar o resto.
  /// A explicação continua disponível no tooltip.
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (label, icon, foreground, background) = connected
        ? (
            'Principal',
            Icons.lan_outlined,
            const Color(0xFF167A3E),
            const Color(0xFFE8F7EE),
          )
        : (
            'Sem o Principal',
            Icons.lan_outlined,
            scheme.error,
            scheme.errorContainer,
          );

    final content = Container(
      height: 38,
      padding: EdgeInsets.symmetric(horizontal: compact ? 9 : 11),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: foreground.withValues(alpha: .18)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 17, color: foreground),
          if (!compact) ...[
            const SizedBox(width: 7),
            Text(
              label,
              style: TextStyle(
                color: foreground,
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ],
      ),
    );
    return Tooltip(
      message: connected
          ? 'Conectado ao Caixa Principal. $detail'
          : 'Este caixa é secundário e não altera pedidos sem o Caixa '
                'Principal, para não gerar divergência. $detail',
      child: onPressed == null
          ? content
          : InkWell(
              onTap: onPressed,
              borderRadius: BorderRadius.circular(10),
              child: content,
            ),
    );
  }
}

class _DestinationButton extends StatelessWidget {
  const _DestinationButton({
    required this.entry,
    required this.expanded,
    required this.selected,
    required this.onTap,
  });

  final _SidebarEntry entry;
  final bool expanded;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final foreground = selected ? scheme.onPrimary : scheme.onSurfaceVariant;
    final button = Material(
      color: selected ? scheme.primary : Colors.transparent,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: SizedBox(
          height: 46,
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: expanded ? 13 : 0),
            child: Row(
              mainAxisAlignment: expanded
                  ? MainAxisAlignment.start
                  : MainAxisAlignment.center,
              children: [
                Icon(entry.icon, size: 21, color: foreground),
                if (expanded) ...[
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      entry.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: foreground,
                        fontSize: 13,
                        fontWeight: selected
                            ? FontWeight.w800
                            : FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
    return expanded ? button : Tooltip(message: entry.label, child: button);
  }
}

class _SidebarAction extends StatelessWidget {
  const _SidebarAction({
    required this.expanded,
    required this.label,
    required this.icon,
    required this.onTap,
  });

  final bool expanded;
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final child = Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(10),
        child: SizedBox(
          height: 44,
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: expanded ? 13 : 0),
            child: Row(
              mainAxisAlignment: expanded
                  ? MainAxisAlignment.start
                  : MainAxisAlignment.center,
              children: [
                Icon(icon, size: 20, color: scheme.onSurfaceVariant),
                if (expanded) ...[
                  const SizedBox(width: 12),
                  Text(
                    label,
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
    return expanded ? child : Tooltip(message: label, child: child);
  }
}

class _SidebarEntry {
  const _SidebarEntry({
    required this.destination,
    required this.label,
    required this.icon,
  });

  final PdvDestination destination;
  final String label;
  final IconData icon;
}
