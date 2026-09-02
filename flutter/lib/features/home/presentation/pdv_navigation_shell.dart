import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/network/api_client.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/pdv_update_service.dart';

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
    required this.userSubtitle,
    required this.onLogout,
    this.contextPanel,
    this.compactContextPanel,
    this.showOrders = true,
    this.showFinance = true,
    this.showScale = true,
    this.showSettings = true,
    this.versionStatus,
    this.onCheckVersion,
  });

  final bool expanded;
  final PdvDestination selected;
  final VoidCallback onToggle;
  final ValueChanged<PdvDestination> onSelected;
  final String userName;
  final String userSubtitle;
  final VoidCallback onLogout;
  final Widget? contextPanel;
  final Widget? compactContextPanel;
  final bool showOrders;
  final bool showFinance;
  final bool showScale;
  final bool showSettings;
  final PdvUpdateStatus? versionStatus;
  final VoidCallback? onCheckVersion;

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
      if (showFinance)
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
      width: expanded ? 236 : 72,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border(right: BorderSide(color: scheme.outlineVariant)),
        ),
        child: SafeArea(
          right: false,
          child: Column(
            children: [
              Padding(
                padding: EdgeInsets.fromLTRB(
                  expanded ? 16 : 12,
                  16,
                  expanded ? 16 : 12,
                  14,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      mainAxisAlignment: expanded
                          ? MainAxisAlignment.start
                          : MainAxisAlignment.center,
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          padding: const EdgeInsets.all(6),
                          decoration: BoxDecoration(
                            color: scheme.primaryContainer,
                            borderRadius: AppTheme.radius,
                            border: Border.all(color: scheme.outlineVariant),
                          ),
                          child: Image.asset(
                            'assets/logoicon.png',
                            filterQuality: FilterQuality.high,
                          ),
                        ),
                        if (expanded) ...[
                          const SizedBox(width: 10),
                          Expanded(
                            child: _PdvVersionIndicator(
                              status: versionStatus,
                              onPressed: onCheckVersion,
                            ),
                          ),
                        ],
                      ],
                    ),
                    if (expanded) ...[
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          CircleAvatar(
                            radius: 17,
                            backgroundColor: scheme.surfaceContainer,
                            foregroundColor: scheme.onSurface,
                            child: Text(
                              _initials(userName),
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ),
                          const SizedBox(width: 9),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  userName,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                Text(
                                  userSubtitle,
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
                      if (contextPanel != null) ...[
                        const SizedBox(height: 12),
                        contextPanel!,
                      ],
                    ] else if (compactContextPanel != null) ...[
                      const SizedBox(height: 12),
                      Center(child: compactContextPanel!),
                    ],
                  ],
                ),
              ),
              Divider(height: 1, color: scheme.outlineVariant),
              if (expanded)
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
                  child: Text(
                    'NAVEGAÇÃO',
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 9,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 1.1,
                    ),
                  ),
                )
              else
                const SizedBox(height: 10),
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
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
                child: Column(
                  children: [
                    _SidebarAction(
                      expanded: expanded,
                      label: expanded ? 'Recolher menu' : 'Expandir menu',
                      icon: expanded
                          ? Icons.keyboard_double_arrow_left
                          : Icons.keyboard_double_arrow_right,
                      onTap: onToggle,
                    ),
                    const SizedBox(height: 3),
                    _SidebarAction(
                      expanded: expanded,
                      label: 'Sair',
                      icon: Icons.logout,
                      onTap: onLogout,
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

class _PdvVersionIndicator extends StatelessWidget {
  const _PdvVersionIndicator({required this.status, this.onPressed});

  final PdvUpdateStatus? status;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final installedVersion = status?.installed?.version;
    final label = installedVersion == null
        ? 'STARCHEF'
        : 'STARCHEF v$installedVersion';
    final (icon, color, stateLabel) = switch (status?.phase) {
      PdvUpdatePhase.checking => (
        Icons.sync_rounded,
        scheme.onSurfaceVariant,
        'Verificando atualização',
      ),
      PdvUpdatePhase.upToDate => (
        Icons.check_circle,
        const Color(0xFF16A34A),
        'Atualizado',
      ),
      PdvUpdatePhase.updateAvailable => (
        Icons.cancel,
        const Color(0xFFDC2626),
        'Desatualizado · v${status?.latestVersion} disponível',
      ),
      PdvUpdatePhase.unavailable => (
        Icons.help_outline,
        scheme.onSurfaceVariant,
        'Atualização não verificada',
      ),
      null => (null, scheme.onSurfaceVariant, 'Versão não verificada'),
    };
    final tooltip = [
      stateLabel,
      if (status?.detail != null) status!.detail!,
      if (onPressed != null) 'Clique para verificar novamente.',
    ].join('\n');

    return Row(
      children: [
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: scheme.primary,
              fontSize: 13,
              fontWeight: FontWeight.w900,
              letterSpacing: .35,
            ),
          ),
        ),
        if (icon != null) ...[
          const SizedBox(width: 5),
          Tooltip(
            message: tooltip,
            child: InkResponse(
              onTap: onPressed,
              radius: 15,
              child: Padding(
                padding: const EdgeInsets.all(2),
                child: Icon(icon, size: 16, color: color),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

/// O indicador de conexão da barra, com histerese.
///
/// O estado real oscila por motivos legítimos e curtos: uma venda entra na
/// fila e sai 300ms depois, um GET falha e o seguinte passa, o ciclo de
/// entrega abre e fecha. Pintar cada oscilação transformava o indicador num
/// pisca-pisca — o operador vê movimento o tempo todo, para de ler, e o aviso
/// que importa (offline, fila para revisar) se perde no ruído.
///
/// Então: uma fase nova só é pintada depois de se manter por [_settle], e uma
/// fase pintada permanece por pelo menos [_minDwell]. Contadores dentro da
/// MESMA fase ("Sincronizando 3" → "Sincronizando 2") passam na hora, porque
/// aí o movimento é a informação. O primeiro estado nunca espera: abrir o PDV
/// mostrando a verdade imediatamente é o certo.
class PdvConnectionBadge extends StatefulWidget {
  const PdvConnectionBadge({super.key, required this.status, this.onPressed});

  final NetworkSyncStatus status;
  final VoidCallback? onPressed;

  /// Quanto tempo uma fase precisa se manter para valer a repintura.
  static const _settle = Duration(milliseconds: 1200);

  /// Quanto tempo uma fase pintada fica na tela antes de poder ser trocada.
  static const _minDwell = Duration(seconds: 2);

  @override
  State<PdvConnectionBadge> createState() => _PdvConnectionBadgeState();
}

class _PdvConnectionBadgeState extends State<PdvConnectionBadge> {
  late NetworkSyncStatus _shown = widget.status;
  late DateTime _shownAt = DateTime.now();
  Timer? _settleTimer;

  @override
  void didUpdateWidget(PdvConnectionBadge oldWidget) {
    super.didUpdateWidget(oldWidget);
    final incoming = widget.status;
    if (incoming == _shown) {
      // Voltou para o que já está na tela antes de assentar: a oscilação
      // simplesmente não aconteceu, do ponto de vista de quem olha.
      _settleTimer?.cancel();
      _settleTimer = null;
      return;
    }
    if (incoming.phase == _shown.phase) {
      _settleTimer?.cancel();
      _settleTimer = null;
      setState(() => _shown = incoming);
      return;
    }
    final held = DateTime.now().difference(_shownAt);
    final remaining = PdvConnectionBadge._minDwell - held;
    final wait = remaining > PdvConnectionBadge._settle
        ? remaining
        : PdvConnectionBadge._settle;
    _settleTimer?.cancel();
    _settleTimer = Timer(wait, () {
      if (!mounted) return;
      setState(() {
        _shown = widget.status;
        _shownAt = DateTime.now();
      });
    });
  }

  @override
  void dispose() {
    _settleTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      _ConnectionBadgeView(status: _shown, onPressed: widget.onPressed);
}

class _ConnectionBadgeView extends StatelessWidget {
  const _ConnectionBadgeView({required this.status, this.onPressed});

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
        Colors.white,
        const Color(0xFF166534),
      ),
    };
    final hoverBackground = status.phase == NetworkSyncPhase.online
        ? const Color(0xFF14532D)
        : null;

    final content = ShadBadge.raw(
      variant: ShadBadgeVariant.outline,
      onPressed: onPressed,
      padding: const EdgeInsets.symmetric(horizontal: 11),
      backgroundColor: background,
      hoverBackgroundColor: hoverBackground,
      foregroundColor: foreground,
      shape: RoundedRectangleBorder(
        borderRadius: AppTheme.radius,
        side: BorderSide(color: foreground.withValues(alpha: .18)),
      ),
      child: SizedBox(
        height: 36,
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
      child: content,
    );
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

    final content = ShadBadge.raw(
      variant: ShadBadgeVariant.outline,
      onPressed: onPressed,
      padding: EdgeInsets.symmetric(horizontal: compact ? 9 : 11),
      backgroundColor: background,
      foregroundColor: foreground,
      shape: RoundedRectangleBorder(
        borderRadius: AppTheme.radius,
        side: BorderSide(color: foreground.withValues(alpha: .18)),
      ),
      child: SizedBox(
        height: 36,
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
      ),
    );
    return Tooltip(
      message: connected
          ? 'Conectado ao Caixa Principal. $detail'
          : 'Este caixa é secundário e não altera pedidos sem o Caixa '
                'Principal, para não gerar divergência. $detail',
      child: content,
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
    final button = ShadButton.raw(
      variant: selected ? ShadButtonVariant.primary : ShadButtonVariant.ghost,
      onPressed: onTap,
      width: expanded ? 204 : 56,
      height: 46,
      padding: EdgeInsets.symmetric(horizontal: expanded ? 13 : 0),
      foregroundColor: foreground,
      hoverForegroundColor: selected ? scheme.onPrimary : scheme.onSurface,
      expands: expanded,
      mainAxisAlignment: expanded
          ? MainAxisAlignment.start
          : MainAxisAlignment.center,
      leading: Icon(entry.icon, size: 20),
      child: expanded
          ? Text(
              entry.label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 13,
                fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
              ),
            )
          : null,
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
    final child = ShadButton.ghost(
      onPressed: onTap,
      width: expanded ? 204 : 56,
      height: 44,
      padding: EdgeInsets.symmetric(horizontal: expanded ? 13 : 0),
      foregroundColor: scheme.onSurfaceVariant,
      hoverForegroundColor: scheme.onSurface,
      expands: expanded,
      mainAxisAlignment: expanded
          ? MainAxisAlignment.start
          : MainAxisAlignment.center,
      leading: Icon(icon, size: 20),
      child: expanded
          ? Text(label, style: const TextStyle(fontWeight: FontWeight.w700))
          : null,
    );
    return Tooltip(message: label, child: child);
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
