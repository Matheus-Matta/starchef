import 'package:flutter/material.dart';

import '../../../core/config/api_settings.dart';
import '../../../core/sync/backend_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/manual_update_action.dart';
import '../../../core/update/update_banner.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../auth/presentation/session_controller.dart';
import '../../printing/presentation/print_status_page.dart';
import '../../printing/services/mobile_print_agent.dart';
import '../../settings/presentation/api_settings_page.dart';
import '../data/orders_repository.dart';
import 'ask_table_toggle.dart';
import 'orders_page_navigation.dart';
import 'comandas_grade.dart';
import 'comandas_presenter.dart';
import 'pending_sheet.dart';
import 'cloud_mode_banner.dart';
import 'stale_data_banner.dart';
import 'sync_banner.dart';

part 'orders_page_components.dart';

/// Tela inicial: TODAS as comandas, para o garçom tocar e lançar.
///
/// O app serve só para lançar em comanda: não há mais "Novo pedido". Tocar no
/// cartão abre o cardápio direto — é o caminho mais curto até o item.
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
  ComandasPresenter get presenter => _presenter;

  late final _presenter = ComandasPresenter(repository: widget.repository);

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

  Future<void> _checkUpdates() => checkMobileUpdateNow(context);
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
      title: 'Comandas',
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
          settings: widget.settings,
          onPrinting: _openPrinting,
          onCustomers: openCustomers,
          onUpdates: _checkUpdates,
        ),
      ],
      banners: [
        const UpdateBanner(),
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
      body: ComandasGrade(
        presenter: _presenter,
        gateway: _gateway,
        onOpen: openCommand,
      ),
    ),
  );
}
