import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/config/api_settings.dart';
import '../../../core/sync/backend_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../auth/presentation/session_controller.dart';
import '../../printing/presentation/print_status_page.dart';
import '../../printing/services/mobile_print_agent.dart';
import '../../settings/presentation/api_settings_page.dart';
import '../data/orders_repository.dart';
import 'new_order_flow.dart';
import 'order_card.dart';
import 'order_detail_page.dart';
import 'orders_presenter.dart';
import 'pending_sheet.dart';
import 'stale_data_banner.dart';
import 'sync_banner.dart';

part 'orders_page_components.dart';

/// Tela inicial: os pedidos abertos do salão.
///
/// Aqui só existe tela — carregar, saber de onde veio o dado e traduzir falha
/// é do [OrdersPresenter]; abrir um pedido novo, do [startNewOrder].
class OrdersPage extends StatefulWidget {
  const OrdersPage({
    super.key,
    required this.controller,
    required this.repository,
    required this.settings,
    required this.printAgent,
  });

  final SessionController controller;
  final OrdersRepository repository;
  final ApiSettings settings;
  final MobilePrintAgent printAgent;

  @override
  State<OrdersPage> createState() => _OrdersPageState();
}

class _OrdersPageState extends State<OrdersPage> {
  late final _presenter = OrdersPresenter(repository: widget.repository);

  BackendGateway get _gateway => widget.repository.gateway;

  @override
  void initState() {
    super.initState();
    _presenter.load();
  }

  @override
  void dispose() {
    _presenter.dispose();
    super.dispose();
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
    if (mounted) await _presenter.load();
  }

  Future<void> _newOrder() async {
    final order = await startNewOrder(context, widget.repository);
    if (order != null && mounted) await _openOrder(order);
  }

  Future<void> _openApiSettings() async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute<bool>(
        builder: (_) => ApiSettingsPage(settings: widget.settings),
      ),
    );
    if (changed == true) await widget.controller.logout();
  }

  Future<void> _openPrinting() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => PrintStatusPage(agent: widget.printAgent),
    ),
  );

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    // Um só builder para a tela inteira. A fila, os itens ainda não enviados
    // e a atualização mudam ao mesmo tempo o contador do topo, as faixas e os
    // cartões — separá-los em três builders aninhados só escondia isso.
    animation: Listenable.merge([
      _presenter,
      _gateway,
      widget.repository.drafts,
      widget.printAgent,
    ]),
    builder: (context, _) => AppPageScaffold(
      title: 'Pedidos abertos',
      actions: [
        _PendingCounter(
          gateway: _gateway,
          onPressed: () => showPendingSheet(context, _gateway),
        ),
        IconButton(
          tooltip: 'Atualizar',
          onPressed: _presenter.loading ? null : _presenter.load,
          icon: const Icon(Icons.refresh),
        ),
        _AccountMenu(
          controller: widget.controller,
          onApiSettings: _openApiSettings,
          onPrinting: _openPrinting,
        ),
      ],
      banners: [
        StaleDataBanner(
          origin: _presenter.origin,
          onRetry: _presenter.loading ? null : _presenter.load,
        ),
        SyncBanner(
          gateway: _gateway,
          onOpenFailed: () => showPendingSheet(context, _gateway),
        ),
      ],
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _newOrder,
        icon: const Icon(Icons.add),
        label: const Text('Novo pedido'),
      ),
      body: RefreshIndicator(onRefresh: _presenter.load, child: _body()),
    ),
  );

  Widget _body() {
    final orders = _presenter.orders;
    final creating = _presenter.creatingOrders.length;
    if (orders.isNotEmpty) {
      return _OrdersList(
        orders: orders,
        repository: widget.repository,
        onOpen: _openOrder,
      );
    }
    if (_presenter.loading && creating == 0) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_presenter.error != null && creating == 0) {
      return AppEmptyState(
        scrollable: true,
        icon: Icons.wifi_off,
        title: 'Não foi possível carregar',
        description: _presenter.error!,
        action: ShadButton.outline(
          onPressed: _presenter.load,
          child: const Text('Tentar de novo'),
        ),
      );
    }
    // Com pedidos ainda a caminho, dizer "nenhum pedido aberto" faria o garçom
    // achar que o que ele acabou de lançar se perdeu.
    if (creating > 0) {
      return AppEmptyState(
        scrollable: true,
        icon: Icons.cloud_upload_outlined,
        title: 'Pedido a caminho do servidor',
        description:
            '$creating pedido(s) lançado(s) neste aparelho ainda não foram '
            'confirmados pelo backend.',
        action: ShadButton.outline(
          onPressed: () => showPendingSheet(context, _gateway),
          child: const Text('Ver envios pendentes'),
        ),
      );
    }
    return const AppEmptyState(
      scrollable: true,
      icon: Icons.receipt_long_outlined,
      title: 'Nenhum pedido aberto',
      description: 'Toque em "Novo pedido" para começar a atender uma mesa.',
    );
  }
}
