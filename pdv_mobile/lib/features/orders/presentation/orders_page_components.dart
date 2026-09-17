part of 'orders_page.dart';

/// Só pedidos confirmados: o que este aparelho ainda deve mandar vive atrás do
/// contador do topo ([showPendingSheet]), onde diz em que pé está.
class _OrdersList extends StatelessWidget {
  const _OrdersList({
    required this.orders,
    required this.repository,
    required this.onOpen,
  });

  final List<Map<String, dynamic>> orders;
  final OrdersRepository repository;
  final ValueChanged<Map<String, dynamic>> onOpen;

  @override
  Widget build(BuildContext context) => ListView.separated(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
    physics: const AlwaysScrollableScrollPhysics(),
    itemCount: orders.length,
    separatorBuilder: (_, _) => const SizedBox(height: AppTheme.gap),
    itemBuilder: (context, index) {
      final order = orders[index];
      final orderId = '${order['id'] ?? ''}';
      return OrderCard(
        order: order,
        failed: repository.gateway.failedFor(orderId).length,
        draft: repository.drafts.countFor(orderId),
        onTap: () => onOpen(order),
      );
    },
  );
}

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
  });

  final SessionController controller;
  final VoidCallback onApiSettings;
  final VoidCallback onPrinting;

  @override
  Widget build(BuildContext context) {
    final user = controller.session?.user;
    return PopupMenuButton<String>(
      tooltip: 'Conta',
      onSelected: (value) => switch (value) {
        'api' => onApiSettings(),
        'printing' => onPrinting(),
        'sair' => controller.logout(),
        _ => null,
      },
      itemBuilder: (context) => [
        _info('${user?.displayName ?? ''}\n${user?.restaurantName ?? ''}'),
        const PopupMenuDivider(),
        const PopupMenuItem(
          value: 'printing',
          child: Text('Impressoras e fila'),
        ),
        const PopupMenuItem(value: 'api', child: Text('Servidor da API')),
        const PopupMenuItem(value: 'sair', child: Text('Sair')),
      ],
    );
  }

  PopupMenuItem<String> _info(String text) => PopupMenuItem(
    enabled: false,
    child: Text(text, style: const TextStyle(fontSize: 12)),
  );
}
