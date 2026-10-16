part of 'orders_page.dart';

/// Quanto este aparelho ainda deve ao backend.
class _PendingCounter extends StatelessWidget {
  const _PendingCounter({required this.gateway, required this.onPressed});

  final BackendGateway gateway;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final total = gateway.pendingCount + gateway.failed.length;
    return IconButton(
      tooltip: 'Envios pendentes',
      onPressed: onPressed,
      icon: Badge(
        isLabelVisible: total > 0,
        backgroundColor: gateway.failed.isEmpty
            ? AppColors.warning
            : AppColors.danger,
        label: Text('$total'),
        child: const Icon(Icons.cloud_upload_outlined),
      ),
    );
  }
}

class _AccountMenu extends StatelessWidget {
  const _AccountMenu({
    required this.controller,
    required this.onApiSettings,
    required this.onPrinting,
    required this.onCustomers,
    required this.onUpdates,
    required this.settings,
  });

  final SessionController controller;

  /// Lido quando o menu ABRE: o ✓ de "Perguntar mesa" sai sempre atual.
  final ApiSettings settings;
  final VoidCallback onApiSettings;
  final VoidCallback onPrinting;
  final VoidCallback onCustomers;
  final VoidCallback onUpdates;

  @override
  Widget build(BuildContext context) {
    final user = controller.session?.user;
    return PopupMenuButton<String>(
      tooltip: 'Conta',
      onSelected: (value) => switch (value) {
        'clientes' => onCustomers(),
        'api' => onApiSettings(),
        'printing' => onPrinting(),
        'updates' => onUpdates(),
        'mesa' => alternarPerguntarMesa(context, settings),
        'sair' => controller.logout(),
        _ => null,
      },
      itemBuilder: (context) => [
        _info('${user?.displayName ?? ''}\n${user?.restaurantName ?? ''}'),
        const PopupMenuDivider(),
        // O ITEM FALTAVA. `onSelected` já tratava 'clientes' e a tela existia
        // inteira — sem esta linha o cadastro de cliente não tinha por onde
        // ser aberto no aplicativo, e o código que o abria era inalcançável.
        const PopupMenuItem(value: 'clientes', child: Text('Clientes')),
        const PopupMenuItem(
          value: 'printing',
          child: Text('Impressoras e fila'),
        ),
        // Liga e desliga com um toque, aqui mesmo: é uma escolha da casa
        // (trabalha com mesa ou não), e uma tela só para ela seria demais.
        CheckedPopupMenuItem(
          value: 'mesa',
          checked: settings.askTable,
          child: const Text('Perguntar mesa'),
        ),
        const PopupMenuItem(value: 'api', child: Text('Servidores')),
        const PopupMenuItem(
          value: 'updates',
          child: Text('Buscar atualizações'),
        ),
        const PopupMenuItem(value: 'sair', child: Text('Sair')),
      ],
    );
  }

  PopupMenuItem<String> _info(String text) => PopupMenuItem(
    enabled: false,
    child: Text(text, style: const TextStyle(fontSize: 12)),
  );
}
