import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/garcom_update_controller.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../auth/presentation/principal_setup_page.dart';
import '../../auth/presentation/session_controller.dart';
import '../data/orders_repository.dart';
import 'new_order_flow.dart';
import 'order_card.dart';
import 'order_detail_page.dart';
import 'orders_presenter.dart';
import 'pending_sheet.dart';
import 'stale_data_banner.dart';
import 'sync_banner.dart';
import 'update_banner.dart';
import 'update_dialog.dart';

/// Tela inicial: os pedidos abertos do salão.
///
/// Aqui só existe tela — carregar, saber de onde veio o dado e traduzir falha
/// é do [OrdersPresenter]; abrir um pedido novo, do [startNewOrder].
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
  late final _presenter = OrdersPresenter(repository: widget.repository);
  final _updateController = GarcomUpdateController();

  RelayGateway get _gateway => widget.repository.gateway;

  @override
  void initState() {
    super.initState();
    unawaited(_presenter.load());
    unawaited(_announceUpdate());
  }

  /// Versão nova entra na frente de tudo, assim que o app abre.
  ///
  /// A faixa continua existindo (é o lembrete de quem fechou o diálogo), mas
  /// ela sozinha não dava conta: divide o topo com pendências de envio e
  /// dados de cache, e ninguém para de atender para ler um aviso fino.
  Future<void> _announceUpdate() async {
    await _updateController.checkForUpdate();
    if (!mounted) return;
    if (_updateController.phase != GarcomUpdateBannerPhase.available) return;
    await showGarcomUpdateDialog(context, _updateController);
  }

  @override
  void dispose() {
    _presenter.dispose();
    _updateController.dispose();
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
    if (mounted) await _presenter.load();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    // Um só builder para a tela inteira. A fila, os itens ainda não enviados
    // e a atualização mudam ao mesmo tempo o contador do topo, as faixas e os
    // cartões — separá-los em três builders aninhados só escondia isso.
    animation: Listenable.merge([
      _presenter,
      _gateway,
      widget.repository.drafts,
      _updateController,
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
          onChangePrincipal: _changePrincipal,
        ),
      ],
      banners: [
        UpdateBanner(controller: _updateController),
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
        title: 'Pedido a caminho do caixa',
        description:
            '$creating pedido(s) lançado(s) neste aparelho ainda não foram '
            'confirmados pelo Caixa Principal.',
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

/// Só pedidos do caixa: o que este aparelho ainda deve mandar vive atrás do
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
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: orders.length,
      separatorBuilder: (_, _) => const SizedBox(height: AppTheme.gap),
      itemBuilder: (context, index) {
        final order = orders[index];
        final orderId = '${order['id'] ?? ''}';
        return OrderCard(
          order: order,
          // Itens deste pedido que o caixa recusou: sem o aviso aqui, o garçom
          // só descobria abrindo o pedido — e podia nem abrir.
          failed: repository.gateway.failedFor(orderId).length,
          draft: repository.drafts.countFor(orderId),
          onTap: () => onOpen(order),
        );
      },
    );
  }
}

/// Quanto este aparelho ainda deve ao caixa. É o lugar onde o garçom vê que
/// existe algo pendente sem a lista de pedidos precisar mostrar não-pedidos.
class _PendingCounter extends StatelessWidget {
  const _PendingCounter({required this.gateway, required this.onPressed});

  final RelayGateway gateway;
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
    required this.onChangePrincipal,
  });

  final SessionController controller;
  final VoidCallback onChangePrincipal;

  @override
  Widget build(BuildContext context) {
    final user = controller.session?.user;
    return PopupMenuButton<String>(
      tooltip: 'Conta',
      onSelected: (value) => switch (value) {
        'caixa' => onChangePrincipal(),
        'sair' => controller.logout(),
        _ => null,
      },
      itemBuilder: (context) => [
        _info('${user?.displayName ?? ''}\n${user?.restaurantName ?? ''}'),
        _info('Caixa: ${controller.principal?.host ?? '-'}'),
        const PopupMenuDivider(),
        const PopupMenuItem(
          value: 'caixa',
          child: Text('Trocar Caixa Principal'),
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
