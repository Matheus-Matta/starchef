import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'order_formatters.dart';
import 'orders_page.dart' show describeFailure;

/// Um pedido aberto: o que já foi lançado, o que falta enviar e o que
/// acrescentar.
///
/// **Não há pagamento aqui de propósito.** Receber é do caixa: ele tem a
/// gaveta, a maquininha e a impressora fiscal. O app do garçom para no envio
/// para a cozinha.
class OrderDetailPage extends StatefulWidget {
  const OrderDetailPage({
    super.key,
    required this.repository,
    required this.orderId,
  });

  final OrdersRepository repository;
  final String orderId;

  @override
  State<OrderDetailPage> createState() => _OrderDetailPageState();
}

class _OrderDetailPageState extends State<OrderDetailPage> {
  Map<String, dynamic>? _order;
  bool _loading = true;
  bool _working = false;
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
      final order = await widget.repository.order(widget.orderId);
      if (!mounted) return;
      setState(() {
        _order = order;
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

  /// Executa uma gravação pelo Caixa Principal e recarrega o pedido.
  ///
  /// Recarregar em vez de confiar na resposta é de propósito: o pedido pode ter
  /// mudado no caixa enquanto o garçom estava na mesa, e é a versão do
  /// principal que vale.
  Future<void> _work(Future<void> Function() action, String success) async {
    if (_working) return;
    setState(() => _working = true);
    try {
      await action();
      await _load();
      if (mounted) _toast(success);
    } catch (error) {
      if (mounted) _toast(describeFailure(error));
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _addItem() async {
    final products = await _loadProducts();
    if (products == null || !mounted) return;
    final choice = await showProductPicker(context, products);
    if (choice == null || !mounted) return;
    await _work(
      () => widget.repository.addItem(
        orderId: widget.orderId,
        productId: choice.productId,
        quantity: choice.quantity,
        customerNote: choice.note,
      ),
      'Item lançado.',
    );
  }

  Future<List<Map<String, dynamic>>?> _loadProducts() async {
    try {
      return await widget.repository.products();
    } catch (error) {
      if (mounted) _toast(describeFailure(error));
      return null;
    }
  }

  Future<void> _voidItem(Map<String, dynamic> item) async {
    final reason = await _askReason(item);
    if (reason == null || !mounted) return;
    await _work(
      () => widget.repository.voidItem(
        orderId: widget.orderId,
        itemId: '${item['id']}',
        reason: reason,
      ),
      'Item cancelado.',
    );
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

  Future<void> _sendToKitchen() => _work(
    () => widget.repository.sendToKitchen(widget.orderId),
    'Enviado para a cozinha. O caixa já está imprimindo.',
  );

  void _toast(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final order = _order;
    final pending = order == null ? 0 : pendingItems(order);
    return Scaffold(
      appBar: AppBar(
        title: Text(order == null ? 'Pedido' : orderTitle(order)),
        actions: [
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
              pending: pending,
              busy: _working,
              onAdd: _addItem,
              onSend: pending > 0 ? _sendToKitchen : null,
            ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
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
    if (items.isEmpty) {
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
      itemCount: items.length,
      separatorBuilder: (_, _) => const SizedBox(height: 8),
      itemBuilder: (context, index) => _ItemTile(
        item: items[index],
        onVoid: _working ? null : () => _voidItem(items[index]),
      ),
    );
  }
}

class _ItemTile extends StatelessWidget {
  const _ItemTile({required this.item, this.onVoid});

  final Map<String, dynamic> item;
  final VoidCallback? onVoid;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = '${item['customer_note'] ?? ''}'.trim();
    final pending = item['status'] == 'pending';
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
          // Só item pendente some sem rastro; o que já foi para a cozinha
          // exige cancelamento com motivo — e isso é decisão do caixa.
          if (pending && onVoid != null)
            IconButton(
              tooltip: 'Cancelar item',
              onPressed: onVoid,
              icon: Icon(Icons.close, color: scheme.error, size: 20),
            ),
        ],
      ),
    );
  }
}

class _Actions extends StatelessWidget {
  const _Actions({
    required this.total,
    required this.pending,
    required this.busy,
    required this.onAdd,
    required this.onSend,
  });

  final Object? total;
  final int pending;
  final bool busy;
  final VoidCallback onAdd;
  final VoidCallback? onSend;

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
                Text(
                  'Total',
                  style: TextStyle(color: scheme.onSurfaceVariant),
                ),
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
                    leading: busy
                        ? const SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.send, size: 18),
                    child: Text(
                      pending > 0 ? 'Enviar ($pending)' : 'Tudo enviado',
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
