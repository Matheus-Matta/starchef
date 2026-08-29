import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

/// Painel visual do pedido atual.
///
/// Continua sem dependência de API: recebe dados prontos e comunica intenções
/// por callbacks, mantendo as regras transacionais na tela/controlador do PDV.
class OrderCartPanel extends StatelessWidget {
  const OrderCartPanel({
    super.key,
    required this.order,
    required this.table,
    this.command,
    required this.customer,
    required this.items,
    required this.money,
    required this.onVoidItem,
    required this.onFinish,
    required this.onPrint,
    this.onCancel,
    this.onEmitInvoice,
    required this.printing,
    this.emittingInvoice = false,
    this.selectedItemId,
    this.onSelectItem,
  });

  final Map<String, dynamic>? order;
  final Map<String, dynamic>? table;
  final Map<String, dynamic>? command;
  final Map<String, dynamic>? customer;
  final List<Map<String, dynamic>> items;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onVoidItem;
  final VoidCallback onFinish;
  final VoidCallback onPrint;
  final VoidCallback? onCancel;
  final VoidCallback? onEmitInvoice;
  final bool printing;
  final bool emittingInvoice;

  /// Item sob o cursor do teclado.
  ///
  /// As teclas `+`, `-` e Delete agem sobre ELE. Sem uma seleção visível,
  /// essas teclas teriam de adivinhar um alvo — e uma tecla que apaga não
  /// pode adivinhar.
  final String? selectedItemId;
  final ValueChanged<Map<String, dynamic>>? onSelectItem;

  bool get _readOnly =>
      const {'paid', 'cancelled', 'refunded'}.contains('${order?['status']}');

  /// Item que já saiu da conta e não aceita mais cancelamento — o backend
  /// recusa com "Este item já foi cancelado ou retirado da conta."
  static bool _settled(Map<String, dynamic> item) =>
      const {'cancelled', 'comped'}.contains('${item['status']}');

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ClipRRect(
      borderRadius: AppTheme.radius,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border.all(color: scheme.outlineVariant),
          borderRadius: AppTheme.radius,
        ),
        child: Column(
          children: [
            Container(height: 3, color: scheme.primary),
            _header(context),
            Divider(height: 1, color: scheme.outlineVariant),
            Expanded(child: items.isEmpty ? _empty(context) : _items(context)),
            Divider(height: 1, color: scheme.outlineVariant),
            _footer(context),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pendingOffline = order?['_offline_pending'] == true;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 13, 13, 13),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text(
                'RESUMO DO PEDIDO',
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 9,
                  fontWeight: FontWeight.w900,
                  letterSpacing: .9,
                ),
              ),
              const Spacer(),
              ShadBadge.outline(
                shape: const RoundedRectangleBorder(
                  borderRadius: AppTheme.radius,
                ),
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
                child: Text(
                  _typeLabel('${order?['order_type'] ?? ''}').toUpperCase(),
                  style: const TextStyle(
                    fontSize: 8,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 11),
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: scheme.primaryContainer,
                  borderRadius: AppTheme.radius,
                  border: Border.all(color: scheme.outlineVariant),
                ),
                child: Icon(
                  Icons.receipt_long_outlined,
                  color: scheme.primary,
                  size: 20,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      order == null
                          ? 'Novo pedido'
                          : 'Pedido #${order!['sequence']}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.w900,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _contextLabel(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              if (pendingOffline)
                Tooltip(
                  message:
                      'Pedido salvo localmente e aguardando sincronização.',
                  child: ShadBadge.secondary(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 5,
                    ),
                    backgroundColor: scheme.tertiaryContainer,
                    shape: const RoundedRectangleBorder(
                      borderRadius: AppTheme.radius,
                    ),
                    child: const Text(
                      'LOCAL',
                      style: TextStyle(
                        fontSize: 9,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                ),
              if (order != null && !_readOnly && onCancel != null) ...[
                const SizedBox(width: 4),
                PopupMenuButton<String>(
                  tooltip: 'Mais ações do pedido',
                  icon: const Icon(Icons.more_vert),
                  onSelected: (_) => onCancel?.call(),
                  itemBuilder: (context) => [
                    PopupMenuItem(
                      value: 'cancel',
                      child: Row(
                        children: [
                          Icon(
                            Icons.cancel_outlined,
                            size: 18,
                            color: scheme.error,
                          ),
                          const SizedBox(width: 9),
                          Text(
                            'Cancelar pedido',
                            style: TextStyle(
                              color: scheme.error,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _footer(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final subtotal = order?['subtotal'];
    final serviceFee = _number(order?['service_fee']);
    final deliveryFee = _number(order?['delivery_fee']);
    final discount = _number(order?['discount']);
    return Padding(
      padding: const EdgeInsets.fromLTRB(17, 13, 17, 16),
      child: Column(
        children: [
          _summaryRow(context, 'Subtotal', money(subtotal ?? order?['total'])),
          if (serviceFee.abs() > .009)
            _summaryRow(context, 'Taxa de serviço', money(serviceFee)),
          if (deliveryFee.abs() > .009)
            _summaryRow(context, 'Taxa de entrega', money(deliveryFee)),
          if (discount.abs() > .009)
            _summaryRow(
              context,
              'Desconto',
              '- ${money(discount.abs())}',
              valueColor: scheme.primary,
            ),
          const SizedBox(height: 7),
          Divider(height: 1, color: scheme.outlineVariant),
          const SizedBox(height: 11),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Total',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
              ),
              Text(
                money(order?['total']),
                style: TextStyle(
                  color: scheme.primary,
                  fontSize: 25,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
          const SizedBox(height: 13),
          SizedBox(
            width: double.infinity,
            height: 54,
            child: FilledButton.icon(
              onPressed: order != null && items.isNotEmpty && !_readOnly
                  ? onFinish
                  : null,
              icon: const Icon(Icons.arrow_forward_rounded, size: 21),
              label: Text(
                _readOnly ? 'Pedido somente para consulta' : 'Revisar pedido',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            height: 44,
            child: OutlinedButton.icon(
              onPressed: order != null && items.isNotEmpty && !printing
                  ? onPrint
                  : null,
              icon: printing
                  ? const SizedBox(
                      width: 17,
                      height: 17,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.print_outlined, size: 19),
              label: Text(
                printing ? 'Gerando recibo...' : 'Imprimir recibo de venda',
              ),
            ),
          ),
          if ('${order?['payment_status']}' == 'paid') ...[
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              height: 44,
              child: OutlinedButton.icon(
                onPressed: !emittingInvoice ? onEmitInvoice : null,
                icon: emittingInvoice
                    ? const SizedBox(
                        width: 17,
                        height: 17,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.receipt_long_outlined, size: 19),
                label: Text(
                  emittingInvoice
                      ? 'Emitindo NFC-e...'
                      : 'Emitir NFC-e / Imprimir DANFE',
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _summaryRow(
    BuildContext context,
    String label,
    String value, {
    Color? valueColor,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: scheme.onSurfaceVariant,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: valueColor,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }

  String _contextLabel() {
    final type = '${order?['order_type'] ?? ''}';
    if (command != null) {
      final name = '${command!['customer_name'] ?? ''}'.trim();
      final label = 'Comanda ${command!['number']}';
      final tableLabel = table == null ? '' : ' · Mesa ${table!['number']}';
      final customerLabel = name.isEmpty
          ? (table == null ? ' · Self-service' : '')
          : ' · $name';
      return '$label$tableLabel$customerLabel';
    }
    if (table != null) return 'Mesa ${table!['number']} · Histórico';
    if (customer != null) {
      final phone = '${customer!['phone'] ?? ''}'.trim();
      return phone.isEmpty
          ? '${customer!['name']} · ${_typeLabel(type)}'
          : '${customer!['name']} · $phone';
    }
    final customerName = '${order?['customer_name'] ?? ''}'.trim();
    if (customerName.isNotEmpty) {
      return '$customerName · ${_typeLabel(type)}';
    }
    return _typeLabel(type);
  }

  Widget _empty(BuildContext context) {
    return AppEmptyState(
      icon: Icons.shopping_basket_outlined,
      title: 'O pedido está vazio',
      description: 'Toque em um produto do cardápio para começar.',
    );
  }

  /// Lista os itens agrupados por situação, como no frontend web.
  ///
  /// Separar o que já foi para a produção do que ainda aguarda envio é a
  /// informação que o operador precisa antes de fechar: só a segunda parte
  /// ainda pode ser removida.
  Widget _items(BuildContext context) {
    _pruneItemKeys();
    final sent = items
        .where((item) => item['status'] != 'pending')
        .toList(growable: false);
    final pending = items
        .where((item) => item['status'] == 'pending')
        .toList(growable: false);

    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      children: [
        if (sent.isNotEmpty) ...[
          _sectionLabel(
            context,
            icon: Icons.soup_kitchen_outlined,
            label: 'Em produção (${sent.length})',
          ),
          for (final item in sent)
            Padding(
              key: _keyFor(item),
              padding: const EdgeInsets.only(bottom: 8),
              child: _CartItem(
                item: item,
                money: money,
                selected: '${item['id']}' == selectedItemId,
                onTap: onSelectItem == null ? null : () => onSelectItem!(item),
                // Item já em produção também pode ser cancelado: o backend
                // aceita (`void_order_item`) e emite o cupom de cancelamento
                // para a mesma impressora que recebeu a comanda original
                // (`register_kitchen_item_cancellation_jobs`). Antes o botão
                // simplesmente não existia aqui e o caixa tinha que ligar
                // para a cozinha por fora do sistema. Cortesia e item já
                // cancelado ficam de fora — o backend recusa os dois.
                canRemove: !_readOnly && !_settled(item),
                onRemove: () => onVoidItem(item),
              ),
            ),
        ],
        if (pending.isNotEmpty) ...[
          _sectionLabel(
            context,
            icon: Icons.schedule_outlined,
            label: 'Aguardando envio (${pending.length})',
            highlight: true,
          ),
          for (final item in pending)
            Padding(
              key: _keyFor(item),
              padding: const EdgeInsets.only(bottom: 8),
              child: _CartItem(
                item: item,
                money: money,
                canRemove: !_readOnly,
                onRemove: () => onVoidItem(item),
                selected: '${item['id']}' == selectedItemId,
                onTap: onSelectItem == null ? null : () => onSelectItem!(item),
              ),
            ),
        ],
      ],
    );
  }

  /// Chave estável por item, para a navegação por setas conseguir rolar até
  /// a linha selecionada quando ela sai da área visível.
  static Key _keyFor(Map<String, dynamic> item) =>
      _itemKeys.putIfAbsent('${item['id']}', GlobalKey.new);

  /// Onde a linha deste item está desenhada agora, se estiver.
  static BuildContext? contextOfItem(String itemId) =>
      _itemKeys[itemId]?.currentContext;

  /// Descarta as chaves de itens que saíram da tela.
  ///
  /// Sem isto o mapa guardaria uma `GlobalKey` por item de TODO pedido já
  /// aberto no turno — um vazamento lento que só apareceria depois de horas
  /// de operação, que é exatamente quando ninguém está olhando.
  void _pruneItemKeys() {
    final alive = items.map((item) => '${item['id']}').toSet();
    _itemKeys.removeWhere((id, _) => !alive.contains(id));
  }

  static final Map<String, GlobalKey> _itemKeys = {};

  Widget _sectionLabel(
    BuildContext context, {
    required IconData icon,
    required String label,
    bool highlight = false,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final color = highlight ? scheme.primary : scheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.fromLTRB(2, 4, 2, 7),
      child: Row(
        children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 6),
          Text(
            label.toUpperCase(),
            style: TextStyle(
              color: color,
              fontSize: 10,
              fontWeight: FontWeight.w900,
              letterSpacing: .5,
            ),
          ),
        ],
      ),
    );
  }

  static String _typeLabel(String type) => switch (type) {
    'command' => 'Comanda',
    'table' => 'Mesa (legado)',
    'delivery' => 'Delivery',
    'takeaway' => 'Retirada',
    'counter' => 'Balcão',
    _ => 'Balcão',
  };

  static double _number(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse('${value ?? ''}'.replaceAll(',', '.')) ?? 0;
  }
}

/// Linha do pedido, no mesmo formato do frontend web.
///
/// Sem miniatura do produto: a foto ocupava espaço numa coluna estreita sem
/// ajudar quem já escolheu o item, e uma imagem remota ainda falhava com o
/// terminal offline. O que importa aqui é nome, variações, observação,
/// quantidade e valor.
class _CartItem extends StatelessWidget {
  const _CartItem({
    required this.item,
    required this.canRemove,
    required this.money,
    required this.onRemove,
    this.selected = false,
    this.onTap,
  });

  final Map<String, dynamic> item;
  final bool canRemove;
  final String Function(dynamic) money;
  final VoidCallback onRemove;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = '${item['customer_note'] ?? ''}'.trim();
    final extras = _extras();
    final comped = item['status'] == 'comped';

    final card = ShadCard(
      padding: const EdgeInsets.fromLTRB(11, 9, 7, 9),
      // A seleção precisa ser inconfundível: é ela que diz sobre qual linha
      // o Delete vai agir.
      backgroundColor: selected
          ? scheme.primaryContainer.withValues(alpha: .38)
          : scheme.surface,
      border: selected
          ? ShadBorder.all(color: scheme.primary, width: 1.6)
          : null,
      radius: AppTheme.radius,
      shadows: const [],
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${item['product_name']}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.2,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (extras.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    extras,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
                if (note.isNotEmpty) ...[
                  const SizedBox(height: 3),
                  Text(
                    note,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 10,
                      fontStyle: FontStyle.italic,
                    ),
                  ),
                ],
                // A rodada e o estado na cozinha dependem do item ter saído
                // para produção, não de ele poder ser removido: agora um item
                // em produção mostra os dois (o selo E o botão de cancelar).
                if ('${item['status']}' != 'pending') ...[
                  const SizedBox(height: 5),
                  _statusChip(context),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${_quantityLabel()} ${money(item['unit_price'])}'
                '${item['pricing_unit'] == 'kg' ? '/kg' : ''}',
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                money(item['total_price']),
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w900,
                  decoration: comped ? TextDecoration.lineThrough : null,
                  color: comped ? scheme.onSurfaceVariant : null,
                ),
              ),
            ],
          ),
          if (canRemove)
            SizedBox(
              width: 30,
              height: 30,
              child: IconButton(
                padding: EdgeInsets.zero,
                tooltip: 'Cancelar item',
                onPressed: onRemove,
                icon: const Icon(Icons.close_rounded, size: 17),
              ),
            )
          else
            const SizedBox(width: 30),
        ],
      ),
    );
    if (onTap == null) return card;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: card,
    );
  }

  Widget _statusChip(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final batch = item['batch_number'];
    return Wrap(
      spacing: 5,
      runSpacing: 4,
      children: [
        if (batch != null)
          _chip(context, 'Rodada $batch', scheme.surfaceContainerHigh),
        _chip(
          context,
          _statusLabel('${item['status'] ?? ''}'),
          scheme.secondaryContainer,
        ),
      ],
    );
  }

  Widget _chip(BuildContext context, String label, Color background) =>
      ShadBadge.raw(
        variant: ShadBadgeVariant.secondary,
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        backgroundColor: background,
        foregroundColor: Theme.of(context).colorScheme.onSurface,
        shape: const RoundedRectangleBorder(borderRadius: AppTheme.radius),
        child: Text(
          label,
          style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w800),
        ),
      );

  String _quantityLabel() {
    final quantity = OrderCartPanel._number(item['quantity']);
    if (item['pricing_unit'] == 'kg') {
      return '${quantity.toStringAsFixed(3).replaceAll('.', ',')} kg ×';
    }
    return '${quantity.toStringAsFixed(0)}×';
  }

  /// Variações e adicionais em uma linha, como o frontend web faz.
  String _extras() {
    final parts = <String>[
      for (final variation in (item['variations'] as List? ?? const []))
        if (variation is Map)
          '${variation['name'] ?? ''}'.trim()
        else
          '$variation'.trim(),
      for (final addon in (item['addons'] as List? ?? const []))
        if (addon is Map)
          '${addon['addon_name'] ?? addon['name'] ?? ''}'.trim(),
    ];
    return parts.where((part) => part.isNotEmpty).join(' · ');
  }

  static String _statusLabel(String status) => switch (status) {
    'pending' => 'Pendente',
    'sent' => 'Cozinha',
    'preparing' => 'Preparo',
    'ready' => 'Pronto',
    'delivered' => 'Entregue',
    'cancelled' => 'Cancelado',
    'comped' => 'Cortesia',
    _ => status,
  };
}
