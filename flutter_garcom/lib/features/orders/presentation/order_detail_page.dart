import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/pending_mutation.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'order_formatters.dart';
import 'orders_page.dart' show describeFailure;
import 'payment_sheet.dart';
import 'sync_banner.dart';
import 'table_picker_sheet.dart';

/// Um pedido aberto: o que já foi lançado, o que falta enviar e o que
/// acrescentar.
///
/// O aparelho também opera como **caixa secundário** (§8, §9): fecha a conta
/// e registra recebimentos. Ele nunca fala com a nuvem — entrega a operação ao
/// Caixa Principal, que grava no SQLite dele e sincroniza depois. O que
/// continua sendo só do caixa físico é o que depende de hardware: gaveta,
/// impressora fiscal e o dinheiro em espécie fora de uma sessão aberta.
///
/// **Sem conexão com o Caixa Principal**, lançar item, cancelar item, enviar
/// para a cozinha e vincular mesa ficam salvos no aparelho (ver
/// [RelayGateway]) e aparecem aqui com um selo "aguardando conexão" até o
/// caixa confirmar — a tela nunca trava esperando rede.
class OrderDetailPage extends StatefulWidget {
  const OrderDetailPage({
    super.key,
    required this.repository,
    required this.orderId,
    this.initialOrder,
  });

  final OrdersRepository repository;
  final String orderId;

  /// Pedido já conhecido antes de abrir a tela — obrigatório quando
  /// [orderId] é um id local (`offline-...`, ver [OrdersRepository]): esse
  /// pedido não existe no servidor ainda, então não há nada para buscar até
  /// a criação sincronizar.
  final Map<String, dynamic>? initialOrder;

  @override
  State<OrderDetailPage> createState() => _OrderDetailPageState();
}

class _OrderDetailPageState extends State<OrderDetailPage> {
  Map<String, dynamic>? _order;
  bool _loading = true;
  bool _working = false;
  String? _error;
  int _lastPendingCount = 0;

  /// De onde veio o pedido na tela: do Caixa Principal ou da cópia local.
  ReadOrigin _origin = const ReadOrigin.live();

  /// Recebimentos já registrados neste pedido, vistos pelo Caixa Principal.
  List<Map<String, dynamic>> _payments = const [];
  List<Map<String, dynamic>> _paymentMethods = const [];
  bool _cashRegisterOpen = false;

  /// Id efetivamente usado para buscar/gravar este pedido. Começa igual a
  /// [OrderDetailPage.orderId] e é trocado, sozinho, pelo id real assim que
  /// uma criação offline (id `offline-...`) sincroniza — ver
  /// [_onGatewayChange].
  late String _effectiveOrderId = widget.orderId;

  RelayGateway get _gateway => widget.repository.gateway;

  @override
  void initState() {
    super.initState();
    _order = widget.initialOrder;
    _gateway.addListener(_onGatewayChange);
    _load();
  }

  @override
  void dispose() {
    _gateway.removeListener(_onGatewayChange);
    super.dispose();
  }

  /// Reage à fila offline: uma pendência a menos deste pedido é o sinal de
  /// que o Caixa Principal aceitou alguma coisa — busca a versão real para
  /// substituir a linha otimista pela definitiva. Qualquer outra mudança (uma
  /// pendência a mais, ou de outro pedido) só redesenha o selo.
  void _onGatewayChange() {
    if (!mounted) return;
    if (_effectiveOrderId.startsWith('offline-')) {
      final resolved = _gateway.resolvedOrderId(_effectiveOrderId);
      if (resolved != null) {
        setState(() => _effectiveOrderId = resolved);
        _load();
        return;
      }
    }
    final current = _gateway.pendingFor(_effectiveOrderId).length;
    final flushed = current < _lastPendingCount;
    _lastPendingCount = current;
    if (flushed) {
      _load();
    } else {
      setState(() {});
    }
  }

  Future<void> _load() async {
    // Um pedido criado offline não existe no servidor até a criação
    // sincronizar — não há nada para buscar ainda, então mostra o que já
    // está em memória (o otimista, mais qualquer item lançado offline
    // depois) em vez de tentar um GET que só devolveria 404.
    if (_effectiveOrderId.startsWith('offline-')) {
      setState(() {
        _loading = false;
        _lastPendingCount = _gateway.pendingFor(_effectiveOrderId).length;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final order = await widget.repository.order(_effectiveOrderId);
      if (!mounted) return;
      setState(() {
        _order = order;
        _origin = widget.repository.lastReadOrigin;
        _loading = false;
        _lastPendingCount = _gateway.pendingFor(_effectiveOrderId).length;
      });
      // Fora do caminho crítico: o pedido já está na tela e o garçom pode
      // lançar itens enquanto o contexto de recebimento carrega.
      unawaited(_loadCashierContext());
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = describeFailure(error);
        _loading = false;
      });
    }
  }

  /// Executa uma gravação e recarrega o pedido — a versão do Caixa Principal
  /// é sempre quem manda, mesmo depois de um envio bem-sucedido.
  ///
  /// Uma falha de CONEXÃO não cai no `catch` genérico: [MutationQueued] é a
  /// operação sendo salva com sucesso no aparelho, não um erro — a tela seque
  /// em frente e o selo de pendência (lido do gateway) aparece sozinho.
  Future<void> _work(Future<void> Function() action, String success) async {
    if (_working) return;
    setState(() => _working = true);
    try {
      await action();
      await _load();
      if (mounted) _toast(success);
    } on MutationQueued catch (queued) {
      if (mounted) {
        setState(() {});
        _toast(
          'Sem conexão: "${queued.mutation.summary}" foi salvo e será '
          'enviado quando o Caixa Principal responder.',
        );
      }
    } catch (error) {
      if (mounted) _toast(describeFailure(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _addItem() async {
    final choice = await showProductPicker(context, widget.repository);
    if (choice == null || !mounted) return;
    await _work(
      () => widget.repository.addItem(
        orderId: _effectiveOrderId,
        productId: choice.productId,
        productName: choice.productName,
        quantity: choice.quantity,
        variationId: choice.variationId,
        addonIds: choice.addonIds,
        customerNote: choice.note,
      ),
      'Item lançado.',
    );
  }

  Future<void> _voidItem(Map<String, dynamic> item) async {
    final reason = await _askReason(item);
    if (reason == null || !mounted) return;
    await _work(
      () => widget.repository.voidItem(
        orderId: _effectiveOrderId,
        itemId: '${item['id']}',
        itemLabel: '${item['product_name'] ?? 'item'}',
        reason: reason,
      ),
      'Item cancelado.',
    );
  }

  Future<void> _manageTable() async {
    final order = _order;
    final commandId = '${order?['command'] ?? ''}'.trim();
    if (order == null || commandId.isEmpty || commandId == 'null') return;
    final hasTable =
        '${order['table'] ?? ''}'.trim().isNotEmpty && order['table'] != null;
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.table_restaurant_outlined),
              title: Text(hasTable ? 'Trocar de mesa' : 'Vincular a uma mesa'),
              onTap: () => Navigator.pop(context, 'link'),
            ),
            if (hasTable)
              ListTile(
                leading: const Icon(Icons.link_off_outlined),
                title: const Text('Desvincular da mesa'),
                onTap: () => Navigator.pop(context, 'unlink'),
              ),
          ],
        ),
      ),
    );
    if (action == null || !mounted) return;
    if (action == 'unlink') {
      await _work(
        () => widget.repository.unlinkTable(commandId: commandId),
        'Comanda desvinculada da mesa.',
      );
      return;
    }
    try {
      final tables = await widget.repository.tables();
      if (!mounted) return;
      final table = await showTablePicker(
        context,
        tables,
        commandLabel: orderTitle(order),
      );
      if (table == null || !mounted) return;
      await _work(
        () => widget.repository.linkTable(
          commandId: commandId,
          tableId: '${table['id']}',
          tableLabel: '${table['number']}',
        ),
        hasTable ? 'Comanda transferida de mesa.' : 'Comanda vinculada à mesa.',
      );
    } catch (error) {
      if (mounted) _toast(describeFailure(error));
    }
  }

  Future<String?> _askReason(Map<String, dynamic> item) {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Cancelar ${item['product_name'] ?? 'item'}?'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: 'Motivo',
            hintText: 'Ex.: cliente desistiu',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Voltar'),
          ),
          FilledButton(
            onPressed: () {
              final reason = controller.text.trim();
              if (reason.isEmpty) return;
              Navigator.of(context).pop(reason);
            },
            child: const Text('Cancelar item'),
          ),
        ],
      ),
    );
  }

  /// Total já recebido, somando o que o principal confirmou.
  double get _paid =>
      _payments.fold<double>(0, (total, item) => total + amount(item['amount']));

  double get _remaining {
    final missing = amount(_order?['total']) - _paid;
    return missing < 0 ? 0 : missing;
  }

  Future<void> _receivePayment() async {
    // As formas de pagamento e a sessão de caixa só são consultadas aqui, no
    // momento em que o operador vai receber. Buscá-las a cada abertura de tela
    // custava três consultas ao caixa por pedido — caro no Wi-Fi do salão, e
    // inútil enquanto o garçom está só lançando itens.
    if (_paymentMethods.isEmpty) await _loadPaymentOptions();
    if (!mounted) return;
    if (_paymentMethods.isEmpty) {
      _toast('Formas de pagamento indisponíveis: o caixa não respondeu.');
      return;
    }
    final request = await showPaymentSheet(
      context,
      methods: _paymentMethods,
      remaining: _remaining,
      cashRegisterOpen: _cashRegisterOpen,
    );
    if (request == null || !mounted) return;
    await _work(
      () => widget.repository.pay(
        orderId: _effectiveOrderId,
        paymentMethodId: request.methodId,
        amount: request.amount,
        cashRegisterId: _cashRegisterId,
        reference: request.reference,
      ),
      'Recebimento registrado em ${request.methodName}.',
    );
  }

  String? _cashRegisterId;

  /// Lê o que o recebimento precisa saber, sem prender a tela.
  ///
  /// Tudo vem do Caixa Principal: formas de pagamento, recebimentos já feitos
  /// e a sessão de caixa aberta. Uma falha aqui não impede o garçom de
  /// continuar lançando itens — só esconde o botão de receber.
  Future<void> _loadCashierContext() async {
    // Só depois de a conta fechar: enquanto o pedido está aberto o garçom está
    // lançando item, e o que já foi recebido não muda nada na tela.
    if ('${_order?['status']}' != 'awaiting_payment') return;
    try {
      final payments = await widget.repository.payments(_effectiveOrderId);
      if (!mounted) return;
      setState(() => _payments = payments);
    } catch (_) {
      // O caixa não respondeu: o pedido continua utilizável para lançamento.
    }
  }

  /// Consulta o que só o Caixa Principal sabe: quais formas de pagamento
  /// existem e qual sessão de caixa está aberta.
  Future<void> _loadPaymentOptions() async {
    try {
      final methods = await widget.repository.paymentMethods();
      final session = await widget.repository.currentCashRegister();
      if (!mounted) return;
      setState(() {
        _paymentMethods = methods;
        _cashRegisterId = session == null ? null : '${session['id']}';
        _cashRegisterOpen = _cashRegisterId != null;
      });
    } catch (_) {
      if (mounted) {
        setState(() {
          _paymentMethods = const [];
          _cashRegisterOpen = false;
        });
      }
    }
  }

  Future<void> _sendToKitchen() => _work(
    () => widget.repository.sendToKitchen(_effectiveOrderId),
    'Pedido enviado para produção e impressão.',
  );

  void _toast(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final order = _order;
    final ordersPending = _gateway.pendingFor(_effectiveOrderId);
    final addPending = ordersPending
        .where((m) => m.kind == 'add_item')
        .toList();
    final voidingItemIds = ordersPending
        .where((m) => m.kind == 'void_item')
        .map((m) => m.itemId)
        .whereType<String>()
        .toSet();
    final sendQueued = ordersPending.any((m) => m.kind == 'send_to_kitchen');
    final pending = order == null ? 0 : pendingItems(order) + addPending.length;

    return Scaffold(
      appBar: AppBar(
        title: Text(order == null ? 'Pedido' : orderTitle(order)),
        actions: [
          if (order?['command'] != null)
            IconButton(
              tooltip: 'Vincular ou trocar mesa',
              onPressed: _working ? null : _manageTable,
              icon: const Icon(Icons.table_restaurant_outlined),
            ),
          IconButton(
            tooltip: 'Atualizar',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      bottomNavigationBar: order == null
          ? null
          : _Actions(
              total: order['total'],
              paid: _paid,
              pending: pending,
              busy: _working,
              queued: sendQueued,
              onAdd: _addItem,
              onSend: (pending > 0 && !sendQueued) ? _sendToKitchen : null,
              onReceive:
                  '${order['status']}' == 'awaiting_payment' &&
                      _remaining > 0.009
                  ? _receivePayment
                  : null,
            ),
      body: Column(
        children: [
          StaleDataBanner(origin: _origin, onRetry: _loading ? null : _load),
          Expanded(child: _buildBody(addPending, voidingItemIds)),
        ],
      ),
    );
  }

  Widget _buildBody(
    List<PendingMutation> addPending,
    Set<String> voidingItemIds,
  ) {
    if (_loading && _order == null) {
      return const Center(child: CircularProgressIndicator());
    }
    final order = _order;
    if (order == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error ?? 'Pedido não encontrado.'),
              const SizedBox(height: 16),
              ShadButton.outline(
                onPressed: _load,
                child: const Text('Tentar de novo'),
              ),
            ],
          ),
        ),
      );
    }

    final items = orderItems(order);
    if (items.isEmpty && addPending.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Nenhum item lançado ainda.\nToque em "Adicionar item".',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      itemCount: items.length + addPending.length,
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemBuilder: (context, index) {
        if (index < items.length) {
          final item = items[index];
          final voiding = voidingItemIds.contains('${item['id']}');
          return _ItemTile(
            item: item,
            voiding: voiding,
            onVoid: (_working || voiding) ? null : () => _voidItem(item),
          );
        }
        return _PendingAddTile(mutation: addPending[index - items.length]);
      },
    );
  }
}

class _ItemTile extends StatelessWidget {
  const _ItemTile({required this.item, this.onVoid, this.voiding = false});

  final Map<String, dynamic> item;
  final VoidCallback? onVoid;
  final bool voiding;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = '${item['customer_note'] ?? ''}'.trim();
    final cancellable = !{'cancelled', 'comped'}.contains('${item['status']}');
    return ShadCard(
      radius: AppTheme.radius,
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: scheme.primary.withValues(alpha: .12),
              borderRadius: AppTheme.radius,
            ),
            child: Text(
              '${amount(item['quantity']).toStringAsFixed(0)}x',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: scheme.primary,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${item['product_name'] ?? 'Item'}',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 2),
                Text(
                  '${itemStatusLabel(item['status'])} · '
                  '${money(item['total_price'])}',
                  style: TextStyle(
                    fontSize: 12,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
                if (voiding) ...[
                  const SizedBox(height: 6),
                  const PendingBadge(label: 'cancelando...'),
                ],
                if (note.isNotEmpty && note != 'null') ...[
                  const SizedBox(height: 4),
                  Text(
                    note,
                    style: TextStyle(
                      fontSize: 12,
                      fontStyle: FontStyle.italic,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (cancellable && !voiding && onVoid != null)
            IconButton(
              tooltip: item['status'] == 'queued'
                  ? 'Cancelar antes da impressão'
                  : 'Cancelar item',
              onPressed: onVoid,
              icon: Icon(Icons.close, color: scheme.error, size: 20),
            ),
        ],
      ),
    );
  }
}

/// Item lançado sem conexão: ainda não existe no pedido de verdade, só no
/// aparelho. Some sozinho assim que o Caixa Principal confirma (o pedido é
/// recarregado e essa linha some, virando um item de verdade).
class _PendingAddTile extends StatelessWidget {
  const _PendingAddTile({required this.mutation});

  final PendingMutation mutation;

  @override
  Widget build(BuildContext context) => ShadCard(
    radius: AppTheme.radius,
    columnCrossAxisAlignment: CrossAxisAlignment.stretch,
    child: Row(
      children: [
        Container(
          width: 34,
          height: 34,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.warning.withValues(alpha: .12),
            borderRadius: AppTheme.radius,
          ),
          child: const Icon(
            Icons.hourglass_empty,
            size: 16,
            color: AppColors.warning,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                mutation.summary,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 6),
              const PendingBadge(),
            ],
          ),
        ),
      ],
    ),
  );
}

class _Actions extends StatelessWidget {
  const _Actions({
    required this.total,
    required this.paid,
    required this.pending,
    required this.busy,
    required this.queued,
    required this.onAdd,
    required this.onSend,
    required this.onReceive,
  });

  final Object? total;

  /// Já recebido, somando o que o Caixa Principal confirmou.
  final double paid;
  final int pending;
  final bool busy;

  /// O envio à cozinha já está na fila offline, esperando o caixa responder.
  final bool queued;
  final VoidCallback onAdd;
  final VoidCallback? onSend;

  /// Receber pagamento: o aparelho operando como caixa secundário. `null`
  /// quando o pedido ainda não foi fechado (isso agora só acontece no caixa).
  final VoidCallback? onReceive;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border(top: BorderSide(color: scheme.outlineVariant)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Text('Total', style: TextStyle(color: scheme.onSurfaceVariant)),
                const Spacer(),
                Text(
                  money(total),
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ],
            ),
            if (paid > 0) ...[
              const SizedBox(height: 2),
              Row(
                children: [
                  Text(
                    'Recebido',
                    style: TextStyle(color: scheme.onSurfaceVariant),
                  ),
                  const Spacer(),
                  Text(money(paid)),
                ],
              ),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: ShadButton.outline(
                    onPressed: busy ? null : onAdd,
                    height: AppTheme.controlHeight,
                    leading: const Icon(Icons.add, size: 18),
                    child: const Text('Adicionar item'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: ShadButton(
                    onPressed: busy ? null : onSend,
                    enabled: !busy && onSend != null,
                    height: AppTheme.controlHeight,
                    leading: (busy || queued)
                        ? const SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.send, size: 18),
                    child: Text(
                      queued
                          ? 'Aguardando conexão'
                          : pending > 0
                          ? 'Enviar ($pending)'
                          : 'Tudo enviado',
                    ),
                  ),
                ),
              ],
            ),
            if (onReceive != null) ...[
              const SizedBox(height: 10),
              ShadButton.secondary(
                onPressed: busy ? null : onReceive,
                enabled: !busy,
                height: AppTheme.controlHeight,
                leading: const Icon(Icons.payments_outlined, size: 18),
                child: const Text('Receber'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
