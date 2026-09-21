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
import 'orders_page_navigation.dart';
import 'order_card.dart';
import 'orders_presenter.dart';
import 'pending_sheet.dart';
import 'cloud_mode_banner.dart';
import 'stale_data_banner.dart';
import 'sync_banner.dart';

part 'orders_page_components.dart';

/// Tela inicial: o que está aberto no salão — as comandas em uso e os
/// pedidos abertos.
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

class _OrdersPageState extends State<OrdersPage>
    with OrdersPageNavigation<OrdersPage> {
  @override
  OrdersRepository get repository => widget.repository;
  @override
  OrdersPresenter get presenter => _presenter;

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
      title: 'Salão',
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
        // Antes do aviso de dado velho: "a escrita está indo para outro
        // servidor" muda mais o que o garçom pode fazer do que "a tela mostra
        // um retrato".
        CloudModeBanner(origin: widget.repository.api.lastServerOrigin),
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
        onPressed: openNewFlowResult,
        icon: const Icon(Icons.add),
        label: const Text('Novo pedido'),
      ),
      body: RefreshIndicator(onRefresh: _presenter.load, child: _body()),
    ),
  );

  Widget _body() {
    final creating = _presenter.creatingOrders.length;
    if (!_presenter.isEmpty) {
      return _HomeList(
        orders: _presenter.orders,
        commands: _presenter.commands,
        repository: widget.repository,
        onOpenOrder: openOrder,
        onOpenCommand: openCommand,
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
      title: 'Salão vazio',
      description:
          'Nenhuma comanda em uso e nenhum pedido aberto. Toque em "Novo '
          'pedido" para começar a atender uma mesa.',
    );
  }
}
