part of 'orders_page.dart';

/// A tela inicial inteira: as comandas em uso e os pedidos abertos.
///
/// Separados por rótulo, e não misturados, porque são coisas diferentes para
/// quem lê: a comanda é o que está sendo consumido AGORA e ainda não virou
/// conta; o pedido já é uma conta. É a mesma separação por rótulo que a tela
/// de detalhe usa entre "já na cozinha" e "a enviar" — o garçom já conhece.
///
/// As comandas vêm primeiro: no modelo novo é nelas que ele lança o turno
/// inteiro, e o pedido só nasce no caixa.
///
/// Só o que o backend confirmou aparece aqui: o que este aparelho ainda deve
/// mandar vive atrás do contador do topo ([showPendingSheet]), onde diz em que
/// pé está.
class _HomeList extends StatelessWidget {
  const _HomeList({
    required this.orders,
    required this.commands,
    required this.repository,
    required this.onOpenOrder,
    required this.onOpenCommand,
  });

  final List<Map<String, dynamic>> orders;
  final List<Map<String, dynamic>> commands;
  final OrdersRepository repository;
  final ValueChanged<Map<String, dynamic>> onOpenOrder;
  final ValueChanged<Map<String, dynamic>> onOpenCommand;

  @override
  Widget build(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
    physics: const AlwaysScrollableScrollPhysics(),
    children: [
      if (commands.isNotEmpty) ...[
        AppSectionLabel(
          icon: Icons.receipt_long_outlined,
          label: 'Comandas em uso (${commands.length})',
        ),
        for (final command in commands) _spaced(_commandCard(command)),
        const SizedBox(height: AppTheme.gap),
      ],
      if (orders.isNotEmpty) ...[
        AppSectionLabel(
          icon: Icons.point_of_sale_outlined,
          label: 'Pedidos abertos (${orders.length})',
        ),
        for (final order in orders) _spaced(_orderCard(order)),
      ],
    ],
  );

  Widget _orderCard(Map<String, dynamic> order) {
    final id = '${order['id'] ?? ''}';
    return OrderCard(
      order: order,
      failed: repository.gateway.failedFor(id).length,
      draft: repository.drafts.countFor(id),
      onTap: () => onOpenOrder(order),
    );
  }

  Widget _commandCard(Map<String, dynamic> command) {
    final id = '${command['id'] ?? ''}';
    return OrderCard(
      order: commandRowAsSubject(command),
      itemCount: itemCountOf(command),
      // A listagem não diz o que já foi para a produção, então o selo afirma
      // só o que ela garante.
      badgeLabel: 'Em uso',
      failed: repository.gateway.failedFor(id).length,
      draft: repository.drafts.countFor(id),
      onTap: () => onOpenCommand(command),
    );
  }

  static Widget _spaced(Widget child) =>
      Padding(padding: const EdgeInsets.only(bottom: AppTheme.gap), child: child);
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
