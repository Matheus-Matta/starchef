import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/sync/pending_mutation.dart';
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
import 'cloud_mode_banner.dart';
import 'stale_data_banner.dart';

part 'order_detail_items_list.dart';

/// Um atendimento aberto — PEDIDO ou COMANDA: o que já foi lançado, o que
/// falta enviar e o que acrescentar.
///
/// É uma tela só para os dois de propósito. Para o garçom o gesto é o mesmo:
/// abrir, ver o que já foi para a cozinha, acrescentar, mandar a rodada. A
/// comanda teve tela própria por um tempo, e ela nasceu pobre — sem a
/// separação das três listas, sem rascunho, sem os selos da fila. Quem
/// alternava entre as duas no turno reaprendia a tela no meio do salão.
///
/// O que a comanda NÃO tem é recebimento: cobrar é do caixa, que puxa as
/// anotações pendentes para um pedido. Isso cai sozinho — comanda não chega a
/// `awaiting_payment`.
///
/// O aparelho também opera como **caixa secundário** (§8, §9): fecha a conta e
/// registra recebimentos. Ele nunca fala com a nuvem — entrega a operação ao
/// backend, que grava no SQLite dele e sincroniza depois. O que
/// continua sendo só do caixa físico é o que depende de hardware: gaveta,
/// impressora fiscal e o dinheiro em espécie fora de uma sessão aberta.
///
/// Aqui só existe tela. As regras estão no [OrderDetailPresenter], as
/// perguntas em `order_dialogs.dart` e as linhas em `order_item_tiles.dart`.
class OrderDetailPage extends StatefulWidget {
  const OrderDetailPage({
    super.key,
    required this.repository,
    required this.subject,
    this.initialOrder,
    this.canReceivePayment = false,
  });

  final OrdersRepository repository;

  /// O pedido ou a comanda que esta tela está atendendo.
  final OrderSubject subject;

  /// Perfil fixo "Garçom" não recebe pagamento por padrão — só quem tiver
  /// `payments.manage`/`cash.manage` liberado à parte (ver `WaiterUser`).
  final bool canReceivePayment;

  /// Pedido já conhecido antes de abrir a tela — obrigatório quando o id do
  /// [subject] é local (`offline-...`, ver [OrdersRepository]): esse pedido
  /// não existe no servidor ainda, então não há nada para buscar até a criação
  /// sincronizar.
  final Map<String, dynamic>? initialOrder;

  @override
  State<OrderDetailPage> createState() => _OrderDetailPageState();
}

class _OrderDetailPageState extends State<OrderDetailPage> {
  late final _presenter = OrderDetailPresenter(
    repository: widget.repository,
    subject: widget.subject,
    initialOrder: widget.initialOrder,
  );

  /// A sugestão de mesa já apareceu nesta abertura do pedido.
  ///
  /// Por ABERTURA, de propósito: vinculada a mesa, o pedido deixa de estar sem
  /// mesa e a sugestão não tem mais motivo; se o garçom dispensou e voltar
  /// depois com o pedido ainda sem mesa, ela aparece de novo — que é
  /// exatamente quando ela ainda é útil.
  bool _suggestedTable = false;

  @override
  void initState() {
    super.initState();
    _presenter.addListener(_maybeSuggestTable);
    _presenter.start();
  }

  /// Pedido sem mesa: oferece vincular assim que a tela abre.
  ///
  /// A mesa é o que liga a comanda ao salão — sem ela ninguém sabe para onde
  /// levar o pedido. Entrar no pedido e não ser lembrado disso fazia a
  /// correção depender de o garçom lembrar sozinho, no meio do atendimento.
  ///
  /// Não bloqueia: dá para seguir sem mesa (o cliente pode estar em pé), e a
  /// vinculação continua disponível no mesmo botão de sempre.
  void _maybeSuggestTable() {
    if (_suggestedTable || !mounted) return;
    if (!shouldSuggestTable(_presenter.order)) return;
    _suggestedTable = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      final vincular = await confirmLinkTableSuggestion(context);
      if (vincular != true || !mounted) return;
      _report(await manageOrderTable(context, _presenter, skipAsk: true));
    });
  }

  @override
  void dispose() {
    _presenter.removeListener(_maybeSuggestTable);
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
      _report('Formas de pagamento indisponíveis: o servidor não respondeu.');
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
        cardSubtype: request.cardSubtype,
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
        title: order == null
            ? (widget.subject.isCommand ? 'Comanda' : 'Pedido')
            : orderTitle(order),
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
          // Antes do aviso de dado velho: "a escrita está indo para outro
          // servidor" muda mais o que o garçom pode fazer do que "a tela
          // mostra um retrato".
          CloudModeBanner(origin: widget.repository.api.lastServerOrigin),
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

  Widget _actions(Map<String, dynamic> order) {
    // A conta agrupada não existe mais: a comanda é um bloco de notas, e o
    // pedido do caixa puxa as anotações pendentes dela. Não há mais um estado
    // "em fechamento" travando o lançamento do garçom no meio do atendimento.
    return OrderActionsBar(
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
      // Comanda não se cobra aqui, e a checagem é explícita: `awaitingPayment`
      // já seria falso para ela, mas depender disso deixaria o botão a uma
      // mudança de status de distância de aparecer onde não deve.
      onReceive:
          widget.subject.canBeCharged &&
              widget.canReceivePayment &&
              _presenter.awaitingPayment &&
              _presenter.remaining > 0.009
          ? _receivePayment
          : null,
    );
  }

  Widget _body() {
    if (_presenter.loading && _presenter.order == null) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_presenter.order == null) {
      return AppEmptyState(
        icon: Icons.wifi_off,
        title: 'Pedido não encontrado',
        description: _presenter.error ?? 'O backend não respondeu.',
        action: ShadButton.outline(
          onPressed: _presenter.load,
          child: const Text('Tentar de novo'),
        ),
      );
    }
    if (_presenter.isEmpty) {
      // Cartão reutilizado mostra VAZIO, e não o consumo de quem o usou antes:
      // o histórico continua existindo, mas não é o que o garçom pergunta aqui.
      return AppEmptyState(
        icon: Icons.restaurant_menu,
        title: 'Nenhum item lançado ainda',
        description: widget.subject.isCommand
            ? 'Toque em "Adicionar item" para anotar nesta comanda.'
            : 'Toque em "Adicionar item" para começar o pedido.',
      );
    }
    return _ItemsList(
      presenter: _presenter,
      onVoid: _voidItem,
      onDiscard: _discardFailed,
    );
  }
}
