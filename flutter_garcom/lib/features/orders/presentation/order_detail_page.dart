import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/pending_mutation.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'order_actions_bar.dart';
import 'order_detail_presenter.dart';
import 'order_dialogs.dart';
import 'order_formatters.dart';
import 'order_item_tiles.dart';
import 'payment_sheet.dart';
import 'stale_data_banner.dart';

/// Um pedido aberto: o que já foi lançado, o que falta enviar e o que
/// acrescentar.
///
/// O aparelho também opera como **caixa secundário** (§8, §9): fecha a conta e
/// registra recebimentos. Ele nunca fala com a nuvem — entrega a operação ao
/// Caixa Principal, que grava no SQLite dele e sincroniza depois. O que
/// continua sendo só do caixa físico é o que depende de hardware: gaveta,
/// impressora fiscal e o dinheiro em espécie fora de uma sessão aberta.
///
/// Aqui só existe tela. As regras estão no [OrderDetailPresenter], as
/// perguntas em `order_dialogs.dart` e as linhas em `order_item_tiles.dart`.
class OrderDetailPage extends StatefulWidget {
  const OrderDetailPage({
    super.key,
    required this.repository,
    required this.orderId,
    this.initialOrder,
    this.canReceivePayment = false,
  });

  final OrdersRepository repository;
  final String orderId;

  /// Perfil fixo "Garçom" não recebe pagamento por padrão — só quem tiver
  /// `payments.manage`/`cash.manage` liberado à parte (ver `WaiterUser`).
  final bool canReceivePayment;

  /// Pedido já conhecido antes de abrir a tela — obrigatório quando [orderId]
  /// é um id local (`offline-...`, ver [OrdersRepository]): esse pedido não
  /// existe no servidor ainda, então não há nada para buscar até a criação
  /// sincronizar.
  final Map<String, dynamic>? initialOrder;

  @override
  State<OrderDetailPage> createState() => _OrderDetailPageState();
}

class _OrderDetailPageState extends State<OrderDetailPage> {
  late final _presenter = OrderDetailPresenter(
    repository: widget.repository,
    orderId: widget.orderId,
    initialOrder: widget.initialOrder,
  );

  @override
  void initState() {
    super.initState();
    _presenter.start();
  }

  @override
  void dispose() {
    _presenter.dispose();
    super.dispose();
  }

  Future<void> _addItem() async {
    final choice = await showProductPicker(context, widget.repository);
    if (choice != null) await _presenter.addDraft(choice);
  }

  Future<void> _voidItem(Map<String, dynamic> item) async {
    final reason = await askVoidReason(context, item);
    if (reason == null || !mounted) return;
    _report(await _presenter.voidItem(item, reason));
  }

  Future<void> _discardFailed(FailedMutation failure) async {
    if (!await confirmDiscardFailed(context, failure)) return;
    await _presenter.discardFailed(failure);
  }

  /// Recebimento no aparelho, operando como caixa secundário: as formas de
  /// pagamento e a sessão de caixa só são consultadas aqui, no momento em que
  /// o operador vai receber.
  Future<void> _receivePayment() async {
    final available = await _presenter.loadPaymentOptions();
    if (!mounted) return;
    if (!available) {
      _report('Formas de pagamento indisponíveis: o caixa não respondeu.');
      return;
    }
    final request = await showPaymentSheet(
      context,
      methods: _presenter.paymentMethods,
      remaining: _presenter.remaining,
      cashRegisterOpen: _presenter.cashRegisterOpen,
    );
    if (request == null || !mounted) return;
    _report(
      await _presenter.pay(
        methodId: request.methodId,
        methodName: request.methodName,
        value: request.amount,
        reference: request.reference,
      ),
    );
  }

  void _report(String? message) => reportOutcome(context, message);

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: _presenter,
    builder: (context, _) {
      final order = _presenter.order;
      return AppPageScaffold(
        title: order == null ? 'Pedido' : orderTitle(order),
        actions: [
          if (order?['command'] != null)
            IconButton(
              tooltip: 'Vincular ou trocar mesa',
              onPressed: _presenter.working
                  ? null
                  : () async =>
                        _report(await manageOrderTable(context, _presenter)),
              icon: const Icon(Icons.table_restaurant_outlined),
            ),
          IconButton(
            tooltip: 'Atualizar',
            onPressed: _presenter.loading ? null : _presenter.load,
            icon: const Icon(Icons.refresh),
          ),
        ],
        banners: [
          StaleDataBanner(
            origin: _presenter.origin,
            onRetry: _presenter.loading ? null : _presenter.load,
          ),
        ],
        bottomBar: order == null ? null : _actions(order),
        body: _body(),
      );
    },
  );

  Widget _actions(Map<String, dynamic> order) => OrderActionsBar(
    total: order['total'],
    paid: _presenter.paid,
    pending: _presenter.pendingToSend,
    drafts: _presenter.draftItems.length,
    busy: _presenter.working,
    queued: _presenter.sendQueued,
    onAdd: _addItem,
    onSend: (_presenter.pendingToSend > 0 && !_presenter.sendQueued)
        ? () async => _report(await _presenter.sendToKitchen())
        : null,
    onReceive:
        widget.canReceivePayment &&
            _presenter.awaitingPayment &&
            _presenter.remaining > 0.009
        ? _receivePayment
        : null,
  );

  Widget _body() {
    if (_presenter.loading && _presenter.order == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_presenter.order == null) {
      return AppEmptyState(
        icon: Icons.wifi_off,
        title: 'Pedido não encontrado',
        description: _presenter.error ?? 'O Caixa Principal não respondeu.',
        action: ShadButton.outline(
          onPressed: _presenter.load,
          child: const Text('Tentar de novo'),
        ),
      );
    }
    if (_presenter.isEmpty) {
      return const AppEmptyState(
        icon: Icons.restaurant_menu,
        title: 'Nenhum item lançado ainda',
        description: 'Toque em "Adicionar item" para começar o pedido.',
      );
    }
    return _ItemsList(
      presenter: _presenter,
      onVoid: _voidItem,
      onDiscard: _discardFailed,
    );
  }
}

/// As três listas do pedido, na ordem em que o garçom pensa: o que já está na
/// cozinha, o que ele acabou de escolher e ainda não mandou, e o que o caixa
/// recusou. Antes era uma lista só, e "enviado" e "esperando" ficavam
/// indistinguíveis no meio do salão.
class _ItemsList extends StatelessWidget {
  const _ItemsList({
    required this.presenter,
    required this.onVoid,
    required this.onDiscard,
  });

  final OrderDetailPresenter presenter;
  final ValueChanged<Map<String, dynamic>> onVoid;
  final ValueChanged<FailedMutation> onDiscard;

  @override
  Widget build(BuildContext context) {
    final sent = presenter.sentItems;
    final unsent = presenter.unsentItems;
    final drafts = presenter.draftItems;
    final queued = presenter.pendingAdds;
    final failures = presenter.failures;
    final toSend = unsent.length + queued.length + drafts.length;
    final busy = presenter.working;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        if (sent.isNotEmpty) ...[
          const AppSectionLabel(
            icon: Icons.soup_kitchen_outlined,
            label: 'Já na cozinha',
          ),
          for (final item in sent) _spaced(_tile(item)),
        ],
        if (toSend > 0) ...[
          AppSectionLabel(
            icon: Icons.schedule_outlined,
            label: 'A enviar ($toSend)',
          ),
          for (final item in unsent) _spaced(_tile(item)),
          for (final draft in drafts)
            _spaced(
              DraftItemTile(
                item: draft,
                onRemove: busy ? null : () => presenter.removeDraft(draft),
              ),
            ),
          for (final mutation in queued)
            _spaced(QueuedItemTile(mutation: mutation)),
        ],
        if (failures.isNotEmpty) ...[
          const AppSectionLabel(
            icon: Icons.error_outline,
            label: 'Não aceitos pelo caixa',
            color: AppColors.danger,
          ),
          for (final failure in failures)
            _spaced(
              FailedItemTile(
                failure: failure,
                onRetry: busy ? null : () => presenter.retryFailed(failure),
                onDiscard: busy ? null : () => onDiscard(failure),
              ),
            ),
        ],
      ],
    );
  }

  Widget _tile(Map<String, dynamic> item) {
    final voiding = presenter.voidingItemIds.contains('${item['id']}');
    return OrderItemTile(
      item: item,
      voiding: voiding,
      onVoid: (presenter.working || voiding) ? null : () => onVoid(item),
    );
  }

  static Widget _spaced(Widget child) =>
      Padding(padding: const EdgeInsets.only(bottom: 8), child: child);
}
