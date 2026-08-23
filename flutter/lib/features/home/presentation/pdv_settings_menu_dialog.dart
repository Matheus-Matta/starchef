import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

class PdvSettingsMenuDialog extends StatelessWidget {
  const PdvSettingsMenuDialog({
    super.key,
    required this.canManageDevices,
    required this.topologyStatus,
    required this.offlinePendingCount,
    required this.isDark,
    required this.isFullScreen,
  });

  final bool canManageDevices;
  final String topologyStatus;
  final int offlinePendingCount;
  final bool isDark;
  final bool isFullScreen;

  static Future<String?> show(
    BuildContext context, {
    required bool canManageDevices,
    required String topologyStatus,
    required int offlinePendingCount,
    required bool isDark,
    required bool isFullScreen,
  }) => showDialog<String>(
    context: context,
    builder: (_) => PdvSettingsMenuDialog(
      canManageDevices: canManageDevices,
      topologyStatus: topologyStatus,
      offlinePendingCount: offlinePendingCount,
      isDark: isDark,
      isFullScreen: isFullScreen,
    ),
  );

  void _select(BuildContext context, String value) =>
      Navigator.of(context).pop(value);

  @override
  Widget build(BuildContext context) {
    return AppDialog(
      scrollable: true,
      maxWidth: 540,
      title: const Row(
        children: [
          Icon(Icons.settings_outlined),
          SizedBox(width: 10),
          Expanded(child: Text('Configurações do PDV')),
        ],
      ),
      content: SizedBox(
        width: 492,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (canManageDevices) ...[
              _SettingsEntry(
                icon: Icons.print_outlined,
                title: 'Impressoras',
                subtitle: 'Conexão, driver e testes de impressão',
                onTap: () => _select(context, 'printer'),
              ),
              _SettingsEntry(
                icon: Icons.scale_outlined,
                title: 'Balanças',
                subtitle: 'Porta, protocolo e impressora vinculada',
                onTap: () => _select(context, 'scale'),
              ),
              const Divider(),
            ],
            _SettingsEntry(
              icon: Icons.hub_outlined,
              title: 'Rede local de caixas',
              subtitle: topologyStatus,
              onTap: () => _select(context, 'topology'),
            ),
            _SettingsEntry(
              icon: Icons.tune,
              title: 'Preferências deste terminal',
              subtitle: 'Tempo da comanda, estabilidade, alertas e impressão',
              onTap: () => _select(context, 'preferences'),
            ),
            _SettingsEntry(
              icon: Icons.sync_problem_outlined,
              title: 'Operações pendentes',
              subtitle: offlinePendingCount == 0
                  ? 'Nada aguardando o servidor'
                  : '$offlinePendingCount aguardando o servidor',
              onTap: () => _select(context, 'outbox'),
            ),
            const Divider(),
            _SettingsEntry(
              icon: isDark
                  ? Icons.dark_mode_outlined
                  : Icons.light_mode_outlined,
              title: 'Tema escuro',
              subtitle: 'Ajuste visual desta estação',
              trailing: Switch(
                value: isDark,
                onChanged: (_) => _select(context, 'theme'),
              ),
              onTap: () => _select(context, 'theme'),
            ),
            _SettingsEntry(
              icon: isFullScreen ? Icons.fullscreen_exit : Icons.fullscreen,
              title: isFullScreen ? 'Sair da tela cheia' : 'Usar tela cheia',
              subtitle: 'Atalho: F11',
              onTap: () => _select(context, 'fullscreen'),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Fechar'),
        ),
      ],
    );
  }
}

class _SettingsEntry extends StatelessWidget {
  const _SettingsEntry({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4),
      leading: Icon(icon),
      title: Text(title, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(subtitle, maxLines: 2, overflow: TextOverflow.ellipsis),
      trailing: trailing ?? const Icon(Icons.chevron_right),
      onTap: onTap,
    );
  }
}
