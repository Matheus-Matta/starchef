import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../auth/presentation/principal_setup_page.dart';
import '../../auth/presentation/session_controller.dart';
import '../data/orders_repository.dart';
import 'command_picker_sheet.dart';
import 'new_order_sheet.dart';
import 'order_detail_page.dart';
import 'order_formatters.dart';
import 'sync_banner.dart';
import 'table_picker_sheet.dart';

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
    final kind = await showNewOrderSheet(context);
    if (kind == null || !mounted) return;
    if (kind == NewOrderKind.comanda) {
      await _openByCommand();
      return;
    }
    // Balcão, delivery e retirada não passam por comanda: o pedido nasce
    // direto com o tipo escolhido.
    try {
      final order = await widget.repository.createOrder(kind.orderType);
      if (!mounted) return;
      await _openOrder(order);
    } catch (error) {
      if (!mounted) return;
      _toast(describeFailure(error));
    }
  }

  Future<void> _openByCommand() async {
    final command = await showCommandPicker(context, widget.repository);
    if (command == null || !mounted) return;

    late final Map<String, dynamic> order;
    try {
      order = await widget.repository.openCommandOrder('${command['id']}');
    } catch (error) {
      if (!mounted) return;
      _toast(describeFailure(error));
      return;
    }
    if (!mounted) return;

    // Comanda que já estava vinculada a uma mesa não pergunta de novo: o
    // cliente já está sentado, e reperguntar a cada item atrasaria o
    // atendimento.
    final jaVinculada = '${command['current_table'] ?? ''}'.trim();
    if (jaVinculada.isEmpty || jaVinculada == 'null') {
      await _askForTable(command);
      if (!mounted) return;
    }
    await _openOrder(order);
  }

  /// Pergunta a mesa DEPOIS de a comanda estar aberta — o vínculo é do
  /// atendimento, não a forma de abrir o pedido.
  Future<void> _askForTable(Map<String, dynamic> command) async {
    late final List<Map<String, dynamic>> tables;
    try {
      tables = await widget.repository.tables();
    } catch (error) {
      if (!mounted) return;
      _toast(describeFailure(error));
      return;
    }
    if (!mounted) return;
    final table = await showTablePicker(
      context,
      tables,
      commandLabel: 'Comanda ${command['number'] ?? ''}',
    );
    if (table == null || !mounted) return;
    try {
      await widget.repository.linkTable(
        commandId: '${command['id']}',
        tableId: '${table['id']}',
        tableLabel: '${table['number']}',
      );
      if (mounted) _toast('Comanda vinculada à mesa ${table['number']}.');
    } on MutationQueued {
      // Sem conexão com o caixa: o vínculo foi salvo e vai ser reenviado
      // sozinho — não é uma falha do atendimento.
      if (mounted) {
        _toast('Sem conexão: o vínculo com a mesa será enviado assim que o '
            'Caixa Principal responder.');
      }
    } catch (error) {
      // O pedido já existe: falhar o vínculo não pode cancelar o atendimento.
      if (mounted) {
        _toast(
          'Pedido aberto, mas a mesa não foi vinculada: '
          '${describeFailure(error)}',
        );
      }
    }
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
    final gateway = widget.repository.gateway;
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
      body: AnimatedBuilder(
        animation: gateway,
        builder: (context, _) => Column(
          children: [
            SyncBanner(
              gateway: gateway,
              onOpenFailed: () => showFailedMutationsSheet(context, gateway),
            ),
            Expanded(
              child: RefreshIndicator(onRefresh: _load, child: _buildBody()),
            ),
          ],
        ),
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
                    orderSubtitle(order),
                    style: TextStyle(
                      fontSize: 12,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 2),
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
  if (error is MutationQueued) {
    return 'Sem conexão: "${error.mutation.summary}" foi salvo e será '
        'enviado quando o Caixa Principal responder.';
  }
  if (error is PrincipalUnavailable) return error.message;
  if (error is ApiException) return error.message;
  return 'Falha inesperada: $error';
}
