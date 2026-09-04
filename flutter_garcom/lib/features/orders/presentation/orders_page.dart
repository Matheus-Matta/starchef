import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/relay/pending_mutation.dart';
import '../../../core/relay/principal_client.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/garcom_update_controller.dart';
import '../../auth/presentation/principal_setup_page.dart';
import '../../auth/presentation/session_controller.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'command_picker_sheet.dart';
import 'new_order_sheet.dart';
import 'order_detail_page.dart';
import 'order_formatters.dart';
import 'pending_sheet.dart';
import 'sync_banner.dart';
import 'table_picker_sheet.dart';
import 'update_banner.dart';

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

  /// De onde vieram os pedidos na tela: do Caixa Principal ou da cópia local.
  ReadOrigin _origin = const ReadOrigin.live();
  final _updateController = GarcomUpdateController();

  @override
  void initState() {
    super.initState();
    _load();
    unawaited(_updateController.checkForUpdate());
  }

  @override
  void dispose() {
    _updateController.dispose();
    super.dispose();
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
        _origin = widget.repository.lastReadOrigin;
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
          initialOrder: order,
          canReceivePayment:
              widget.controller.session?.user.canReceivePayment ?? false,
        ),
      ),
    );
    if (mounted) await _load();
  }

  /// Pedidos novos ainda não confirmados pelo caixa (fila offline) — sem
  /// isto, sair da tela de detalhe antes de sincronizar faria o pedido
  /// "sumir" até a rede voltar. `RelayGateway.pending` já sobrevive a fechar
  /// e abrir o app (`restore()` na inicialização), então não precisa de
  /// nenhum armazenamento novo aqui.
  List<Map<String, dynamic>> get _creatingOrders => widget
      .repository
      .gateway
      .pending
      .where((mutation) => mutation.kind == 'create_order')
      .map(_placeholderOrder)
      .toList();

  Map<String, dynamic> _placeholderOrder(PendingMutation mutation) {
    final body = mutation.body ?? const <String, dynamic>{};
    final item = body['item'];
    return {
      'id': mutation.placeholderOrderId,
      '_offline_pending': true,
      'status': 'open',
      'order_type': body['order_type'],
      if (body['command'] != null) 'command': body['command'],
      if (body['table'] != null) 'table': body['table'],
      'items': item == null ? const [] : [item],
    };
  }

  Future<void> _newOrder() async {
    final kind = await showNewOrderSheet(context);
    if (kind == null || !mounted) return;
    if (kind == NewOrderKind.comanda) {
      await _openByCommand();
      return;
    }
    final item = await showProductPicker(context, widget.repository);
    if (item == null || !mounted) return;
    try {
      final order = await widget.repository.createOrderWithItem(
        orderType: kind.orderType,
        productId: item.productId,
        quantity: item.quantity,
        variationId: item.variationId,
        addonIds: item.addonIds,
        customerNote: item.note,
      );
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

    final currentOrderId = '${command['current_order_id'] ?? ''}'.trim();
    if (currentOrderId.isNotEmpty && currentOrderId != 'null') {
      await _openOrder({'id': currentOrderId});
      return;
    }

    Map<String, dynamic>? table;
    final jaVinculada = '${command['current_table'] ?? ''}'.trim();
    if (jaVinculada.isEmpty || jaVinculada == 'null') {
      table = await _chooseTable(command);
      if (!mounted) return;
    }
    final item = await showProductPicker(context, widget.repository);
    if (item == null || !mounted) return;
    try {
      final order = await widget.repository.createOrderWithItem(
        orderType: 'command',
        commandId: '${command['id']}',
        tableId: table == null ? null : '${table['id']}',
        productId: item.productId,
        quantity: item.quantity,
        variationId: item.variationId,
        addonIds: item.addonIds,
        customerNote: item.note,
      );
      if (mounted) await _openOrder(order);
    } catch (error) {
      if (mounted) _toast(describeFailure(error));
    }
  }

  /// Pergunta a mesa DEPOIS de a comanda estar aberta — o vínculo é do
  /// atendimento, não a forma de abrir o pedido.
  Future<Map<String, dynamic>?> _chooseTable(
    Map<String, dynamic> command,
  ) async {
    late final List<Map<String, dynamic>> tables;
    try {
      tables = await widget.repository.tables();
    } catch (error) {
      if (!mounted) return null;
      _toast(describeFailure(error));
      return null;
    }
    if (!mounted) return null;
    return showTablePicker(
      context,
      tables,
      commandLabel: 'Comanda ${command['number'] ?? ''}',
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
    final gateway = widget.repository.gateway;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pedidos abertos'),
        actions: [
          // Contador de envios pendentes: é aqui que o garçom vê o que este
          // aparelho ainda deve ao caixa. A lista de pedidos volta a mostrar
          // só pedidos.
          AnimatedBuilder(
            animation: gateway,
            builder: (context, _) {
              final total = gateway.pendingCount + gateway.failed.length;
              return IconButton(
                tooltip: 'Envios pendentes',
                onPressed: () => showPendingSheet(context, gateway),
                icon: Badge(
                  isLabelVisible: total > 0,
                  backgroundColor: gateway.failed.isEmpty
                      ? AppColors.warning
                      : AppColors.danger,
                  label: Text('$total'),
                  child: const Icon(Icons.cloud_upload_outlined),
                ),
              );
            },
          ),
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
        // A fila E os itens ainda não enviados: os dois mudam o que o cartão
        // do pedido mostra, então a lista precisa acompanhar os dois.
        animation: Listenable.merge([gateway, widget.repository.drafts]),
        builder: (context, _) => Column(
          children: [
            ListenableBuilder(
              listenable: _updateController,
              builder: (context, _) =>
                  UpdateBanner(controller: _updateController),
            ),
            StaleDataBanner(origin: _origin, onRetry: _loading ? null : _load),
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
    final creating = _creatingOrders;
    if (_loading && _orders.isEmpty && creating.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _orders.isEmpty && creating.isEmpty) {
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
      // Com pedidos ainda a caminho, dizer "nenhum pedido aberto" faria o
      // garçom achar que o que ele acabou de lançar se perdeu.
      if (creating.isNotEmpty) {
        return _Message(
          icon: Icons.cloud_upload_outlined,
          title: 'Pedido a caminho do caixa',
          description:
              '${creating.length} pedido(s) lançado(s) neste aparelho ainda '
              'não foram confirmados pelo Caixa Principal.',
          action: ShadButton.outline(
            onPressed: () =>
                showPendingSheet(context, widget.repository.gateway),
            child: const Text('Ver envios pendentes'),
          ),
        );
      }
      return const _Message(
        icon: Icons.receipt_long_outlined,
        title: 'Nenhum pedido aberto',
        description: 'Toque em "Novo pedido" para começar a atender uma mesa.',
      );
    }
    // Sem os cartões de "criando": eles não são pedidos do caixa, e sim o que
    // este aparelho ainda deve mandar. Agora vivem atrás do contador do topo
    // (`showPendingSheet`), onde dizem em que pé estão.
    final orders = _orders;
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: orders.length,
      separatorBuilder: (_, _) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final order = orders[index];
        final orderId = '${order['id'] ?? ''}';
        return _OrderCard(
          order: order,
          // Itens deste pedido que o caixa recusou: sem o aviso aqui, o
          // garçom só descobria abrindo o pedido — e podia nem abrir.
          failed: widget.repository.gateway.failedFor(orderId).length,
          draft: widget.repository.drafts.countFor(orderId),
          onTap: () => _openOrder(order),
        );
      },
    );
  }
}

class _OrderCard extends StatelessWidget {
  const _OrderCard({
    required this.order,
    required this.onTap,
    this.failed = 0,
    this.draft = 0,
  });

  final Map<String, dynamic> order;

  /// Itens que o Caixa Principal recusou neste pedido.
  final int failed;

  /// Itens escolhidos e ainda não enviados neste pedido.
  final int draft;

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
            if (failed > 0)
              _CountBadge(
                count: failed,
                color: AppColors.danger,
                icon: Icons.error_outline,
              )
            else if (draft > 0)
              _CountBadge(
                count: draft,
                color: AppColors.warning,
                icon: Icons.schedule_outlined,
              )
            else if (order['_offline_pending'] == true)
              const PendingBadge(label: 'aguardando conexão')
            else
              _StatusChip(order: order),
            const SizedBox(width: 6),
            Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}

/// Contador curto no cartão do pedido: erros de envio ou itens a mandar.
class _CountBadge extends StatelessWidget {
  const _CountBadge({
    required this.count,
    required this.color,
    required this.icon,
  });

  final int count;
  final Color color;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .12),
      borderRadius: AppTheme.radius,
      border: Border.all(color: color.withValues(alpha: .35)),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 4),
        Text(
          '$count',
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w800,
            color: color,
          ),
        ),
      ],
    ),
  );
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
