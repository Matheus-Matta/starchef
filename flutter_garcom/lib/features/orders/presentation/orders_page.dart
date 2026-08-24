import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/theme/app_theme.dart';
import '../../auth/presentation/principal_setup_page.dart';
import '../../auth/presentation/session_controller.dart';
import '../data/orders_repository.dart';
import 'order_detail_page.dart';
import 'order_formatters.dart';

/// Tela inicial: os pedidos abertos do salão.
class OrdersPage extends StatefulWidget {
  const OrdersPage({
    super.key,
    required this.controller,
    required this.repository,
  });

  final SessionController controller;
  final OrdersRepository repository;

  @override
  State<OrdersPage> createState() => _OrdersPageState();
}

class _OrdersPageState extends State<OrdersPage> {
  List<Map<String, dynamic>> _orders = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final orders = await widget.repository.openOrders();
      if (!mounted) return;
      setState(() {
        _orders = orders;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = describeFailure(error);
        _loading = false;
      });
    }
  }

  Future<void> _openOrder(Map<String, dynamic> order) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OrderDetailPage(
          repository: widget.repository,
          orderId: '${order['id']}',
        ),
      ),
    );
    if (mounted) await _load();
  }

  Future<void> _newOrder() async {
    final table = await _pickTable();
    if (table == null || !mounted) return;
    try {
      final order = await widget.repository.openTableOrder('${table['id']}');
      if (!mounted) return;
      await _openOrder(order);
    } catch (error) {
      if (!mounted) return;
      _toast(describeFailure(error));
    }
  }

  Future<Map<String, dynamic>?> _pickTable() async {
    late final List<Map<String, dynamic>> tables;
    try {
      tables = await widget.repository.tables();
    } catch (error) {
      if (!mounted) return null;
      _toast(describeFailure(error));
      return null;
    }
    if (!mounted) return null;
    if (tables.isEmpty) {
      _toast('Nenhuma mesa ativa cadastrada neste restaurante.');
      return null;
    }
    return showModalBottomSheet<Map<String, dynamic>>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => _TablePicker(tables: tables),
    );
  }

  /// Reabre o pareamento sem deslogar: a loja pode ter trocado o computador do
  /// caixa ou gerado uma chave nova no meio do turno.
  Future<void> _changePrincipal() async {
    widget.controller.clearError();
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => ListenableBuilder(
          listenable: widget.controller,
          builder: (context, _) => PrincipalSetupPage(
            controller: widget.controller,
            onDone: () => Navigator.of(context).pop(),
          ),
        ),
      ),
    );
    if (mounted) await _load();
  }

  void _toast(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final user = widget.controller.session?.user;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pedidos abertos'),
        actions: [
          IconButton(
            tooltip: 'Atualizar',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
          PopupMenuButton<String>(
            tooltip: 'Conta',
            onSelected: (value) => switch (value) {
              'caixa' => _changePrincipal(),
              'sair' => widget.controller.logout(),
              _ => null,
            },
            itemBuilder: (context) => [
              PopupMenuItem(
                enabled: false,
                child: Text(
                  '${user?.displayName ?? ''}\n${user?.restaurantName ?? ''}',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
              PopupMenuItem(
                enabled: false,
                child: Text(
                  'Caixa: ${widget.controller.principal?.host ?? '-'}',
                  style: const TextStyle(fontSize: 12),
                ),
              ),
              const PopupMenuDivider(),
              const PopupMenuItem(
                value: 'caixa',
                child: Text('Trocar Caixa Principal'),
              ),
              const PopupMenuItem(value: 'sair', child: Text('Sair')),
            ],
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _newOrder,
        icon: const Icon(Icons.add),
        label: const Text('Novo pedido'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_loading && _orders.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _orders.isEmpty) {
      return _Message(
        icon: Icons.wifi_off,
        title: 'Não foi possível carregar',
        description: _error!,
        action: ShadButton.outline(
          onPressed: _load,
          child: const Text('Tentar de novo'),
        ),
      );
    }
    if (_orders.isEmpty) {
      return const _Message(
        icon: Icons.receipt_long_outlined,
        title: 'Nenhum pedido aberto',
        description: 'Toque em "Novo pedido" para começar a atender uma mesa.',
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: _orders.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final order = _orders[index];
        return _OrderCard(order: order, onTap: () => _openOrder(order));
      },
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({required this.order, required this.onTap});

  final Map<String, dynamic> order;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final items = (order['items'] as List? ?? const []).length;
    return InkWell(
      onTap: onTap,
      borderRadius: AppTheme.radius,
      child: ShadCard(
        radius: AppTheme.radius,
        columnCrossAxisAlignment: CrossAxisAlignment.stretch,
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    orderTitle(order),
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '$items ${items == 1 ? 'item' : 'itens'} · '
                    '${money(order['total'])}',
                    style: TextStyle(
                      fontSize: 13,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
            _StatusChip(order: order),
            const SizedBox(width: 6),
            Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.order});

  final Map<String, dynamic> order;

  @override
  Widget build(BuildContext context) {
    final pending = pendingItems(order);
    final color = pending > 0 ? AppColors.warning : AppColors.success;
    final label = pending > 0 ? '$pending a enviar' : 'Na cozinha';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: AppTheme.radius,
        border: Border.all(color: color.withValues(alpha: .35)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}

class _TablePicker extends StatelessWidget {
  const _TablePicker({required this.tables});

  final List<Map<String, dynamic>> tables;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(20, 4, 20, 12),
          child: Text(
            'Escolha a mesa',
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
        ),
        Flexible(
          child: GridView.builder(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
            shrinkWrap: true,
            gridDelegate:
                const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 120,
                  mainAxisSpacing: 10,
                  crossAxisSpacing: 10,
                  childAspectRatio: 1.3,
                ),
            itemCount: tables.length,
            itemBuilder: (context, index) {
              final table = tables[index];
              final occupied = table['status'] == 'occupied';
              return ShadButton.outline(
                onPressed: () => Navigator.of(context).pop(table),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      'Mesa ${table['number']}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                    if (occupied)
                      const Text('ocupada', style: TextStyle(fontSize: 11)),
                  ],
                ),
              );
            },
          ),
        ),
      ],
    ),
  );
}

class _Message extends StatelessWidget {
  const _Message({
    required this.icon,
    required this.title,
    required this.description,
    this.action,
  });

  final IconData icon;
  final String title;
  final String description;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 80),
      children: [
        Icon(icon, size: 48, color: scheme.onSurfaceVariant),
        const SizedBox(height: 16),
        Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 6),
        Text(
          description,
          textAlign: TextAlign.center,
          style: TextStyle(color: scheme.onSurfaceVariant),
        ),
        if (action != null) ...[
          const SizedBox(height: 20),
          Center(child: action),
        ],
      ],
    );
  }
}

/// Mensagem de falha na linguagem do salão.
String describeFailure(Object error) {
  if (error is PrincipalUnavailable) return error.message;
  if (error is ApiException) return error.message;
  return 'Falha inesperada: $error';
}
