import 'package:flutter/material.dart';

import '../../../core/data/order_item_status.dart';
import 'draft_destination_bar.dart';
import '../../../core/theme/app_theme.dart';
import 'cart_item_card.dart';
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
    this.draftOrderType,
    required this.customer,
    required this.items,
    required this.money,
    required this.onVoidItem,
    this.onFinish,
    required this.onSendToKitchen,
    required this.onPrint,
    this.onCancel,
    this.onMergeCommands,
    this.onRefundMerge,
    this.onEmitInvoice,
    this.onPrintInvoice,
    required this.printing,
    this.emittingInvoice = false,
    this.selectedItemId,
    this.onSelectItem,
    this.onChangeQuantity,
    this.draftTotal,
    this.onPickDraftType,
    this.onAttachCommand,
    this.onDetachCommand,
    this.draftCommands = const [],
    this.draftCommandTotals = const {},
  });

  final Map<String, dynamic>? order;
  final Map<String, dynamic>? table;
  final Map<String, dynamic>? command;
  final String? draftOrderType;
  final Map<String, dynamic>? customer;
  final List<Map<String, dynamic>> items;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onVoidItem;

  /// O total do RASCUNHO, quando ainda não existe pedido no servidor.
  ///
  /// Não dá para tirar de `order`: ele é nulo justamente porque o pedido ainda
  /// não nasceu. E é só conferência — quem soma para cobrar é o servidor, que
  /// conhece taxa de serviço, desconto e o preço em vigor no lançamento.
  final double? draftTotal;

  /// A barra de destino no topo. Nula quando o pedido já existe: aí o destino
  /// está decidido, e trocá-lo não é mais um gesto de tela.
  final ValueChanged<String>? onPickDraftType;
  final VoidCallback? onAttachCommand;
  final ValueChanged<String>? onDetachCommand;

  /// Os cartões anexados ao rascunho e o que cada um já tem lançado.
  final List<Map<String, dynamic>> draftCommands;
  final Map<String, double> draftCommandTotals;

  /// Leva ao pagamento. Nulo para quem não tem a permissão de caixa — e aí o
  /// botão aparece desligado, em vez de sumir ou de não fazer nada ao clique.
  final VoidCallback? onFinish;

  /// Manda para a produção o que ainda não foi — o mesmo que F9 faz.
  ///
  /// Era só uma tecla, e antes disso um caminho escondido dentro do diálogo
  /// de revisão ("Pagar depois"). Quem não decorou a tecla mandava o pedido
  /// para a cozinha passando por uma tela que fala de pagamento.
  final VoidCallback onSendToKitchen;

  final VoidCallback onPrint;
  final VoidCallback? onCancel;

  /// Juntar esta comanda com outras numa conta só.
  ///
  /// `null` quando não faz sentido (não é comanda, o operador não tem
  /// `orders.merge`, ou o pedido já está fechado): a família com quatro
  /// cartões chega ao caixa, e o botão precisa estar do lado do carrinho —
  /// não dentro de um menu, com o cliente esperando.
  final VoidCallback? onMergeCommands;

  /// Estornar a conta agrupada JÁ PAGA de que este pedido é o destino.
  ///
  /// `null` em toda venda comum. Ele aparece no lugar de "Juntar comandas",
  /// que do outro lado do ciclo não teria o que juntar.
  final VoidCallback? onRefundMerge;

  final VoidCallback? onEmitInvoice;

  /// Imprime o DANFE de uma nota que JA existe e esta autorizada.
  final VoidCallback? onPrintInvoice;
  final bool printing;
  final bool emittingInvoice;

  /// Item sob o cursor do teclado.
  ///
  /// As teclas `+`, `-` e Delete agem sobre ELE. Sem uma seleção visível,
  /// essas teclas teriam de adivinhar um alvo — e uma tecla que apaga não
  /// pode adivinhar.
  final String? selectedItemId;
  final ValueChanged<Map<String, dynamic>>? onSelectItem;

  /// Soma ou subtrai unidades de um item que ainda não foi para a produção.
  ///
  /// O contador fica NO CARTÃO, embaixo do nome. Antes, mudar a quantidade
  /// exigia selecionar a linha e usar `+`/`-` no teclado, ou refazer o
  /// lançamento pelo modal — e era por isso que o modal aparecia até para um
  /// refrigerante, que não tem nada a perguntar. Chegando a zero, quem trata
  /// é o cancelamento normal (com motivo e registro), não um apagar em
  /// silêncio.
  final void Function(Map<String, dynamic> item, int delta)? onChangeQuantity;

  /// A altura de TODOS os botões do rodapé.
  ///
  /// Eram 54 para o principal e 44 para o resto, e a diferença não queria
  /// dizer nada além de um ter sido escrito depois do outro.
  static const _alturaBotao = 44.0;

  /// Existe algo para mandar para a produção?
  ///
  /// Mesma regra do F9: só o que está `pending` viaja. Sem nada pendente o
  /// botão fica desligado em vez de mandar uma rodada vazia.
  bool get _hasPendingItems =>
      items.any((item) => '${item['status']}' == 'pending');

  bool get _readOnly =>
      const {'paid', 'cancelled', 'refunded'}.contains('${order?['status']}');

  /// Item que já saiu da conta e não aceita mais cancelamento — o backend
  /// recusa com "Este item já foi cancelado ou retirado da conta."
  static bool _settled(Map<String, dynamic> item) =>
      OrderItemStatus.isOutOfBill(item);

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
            // Só no rascunho: com o pedido aberto o destino já está gravado no
            // servidor, e uma aba que parecesse trocá-lo mentiria.
            if (onPickDraftType != null)
              DraftDestinationBar(
                orderType: draftOrderType ?? 'counter',
                commands: draftCommands,
                totalPorComanda: draftCommandTotals,
                table: table,
                customer: customer,
                enabled: !_readOnly,
                onPickType: onPickDraftType!,
                onAttachCommand: onAttachCommand ?? () {},
                onDetachCommand: onDetachCommand ?? (_) {},
              ),
            Divider(height: 1, color: scheme.outlineVariant),
            Expanded(child: items.isEmpty ? _empty(context) : _items(context)),
            Divider(height: 1, color: scheme.outlineVariant),
            _footer(context),
          ],
        ),
      ),
    );
  }

  /// Conteúdo de um botão de ação: ícone, rótulo e a tecla de atalho.
  ///
  /// A tecla precisa aparecer NO BOTÃO — escondida só na ajuda, ela não é
  /// descoberta por quem já sabe clicar. Mas não pode custar o rótulo: no
  /// painel de 380 px o texto tem de reticenciar em vez de estourar a linha.
  ///
  /// Por isso o layout é montado aqui, e não com `FilledButton.icon`: aquele
  /// construtor põe ícone e rótulo numa `Row` sem `Flexible`, o rótulo recebe
  /// largura infinita, e `TextOverflow.ellipsis` nunca chega a valer. O
  /// sintoma era o botão vazando alguns pixels — o teste de layout estreito
  /// pegou nas duas tentativas anteriores.
  Widget _acaoDoBotao(
    Widget icone,
    String texto, {
    String? tecla,
    double fontSize = 14,
  }) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        icone,
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            texto,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: fontSize, fontWeight: FontWeight.w800),
          ),
        ),
        if (tecla != null) ...[
          const SizedBox(width: 8),
          Text(
            tecla,
            style: TextStyle(fontSize: fontSize - 3, letterSpacing: .4),
          ),
        ],
      ],
    );
  }

  Widget _header(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pendingOffline = order?['_offline_pending'] == true;
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 10, 9),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      order == null
                          ? 'Novo pedido'
                          : 'Pedido #${order?['sequence'] ?? order?['number'] ?? '—'}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _contextLabel,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              if (!_readOnly && onMergeCommands != null)
                TextButton.icon(
                  onPressed: onMergeCommands,
                  icon: const Icon(Icons.call_merge_rounded, size: 17),
                  label: const Text('Juntar comandas'),
                ),
              if (onRefundMerge != null)
                TextButton.icon(
                  onPressed: onRefundMerge,
                  icon: const Icon(Icons.undo_rounded, size: 17),
                  label: const Text('Estornar conta'),
                ),
              if (!_readOnly)
                TextButton.icon(
                  onPressed: onCancel,
                  icon: const Icon(Icons.cancel_outlined, size: 17),
                  label: const Text('Cancelar'),
                ),
            ],
          ),
          if (pendingOffline) ...[
            const SizedBox(height: 7),
            Row(
              children: [
                const Icon(Icons.cloud_upload_outlined, size: 15),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'Salvo neste caixa — sincronização pendente',
                    style: TextStyle(
                      color: scheme.onSurfaceVariant,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  String get _contextLabel => [
    _typeLabel('${order?['order_type'] ?? draftOrderType ?? ''}'),
    if (command != null) 'Comanda ${command?['number']}',
    if (table != null) 'Mesa ${table?['number']}',
    if (customer != null) '${customer?['name'] ?? customer?['display_name']}',
  ].join(' · ');

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
          _summaryRow(
            context,
            'Subtotal',
            money(subtotal ?? order?['total'] ?? draftTotal),
          ),
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
                money(order?['total'] ?? draftTotal),
                style: TextStyle(
                  color: scheme.primary,
                  fontSize: 25,
                  fontWeight: FontWeight.w900,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (_readOnly)
            SizedBox(
              width: double.infinity,
              height: _alturaBotao,
              child: OutlinedButton(
                onPressed: null,
                child: _acaoDoBotao(
                  const Icon(Icons.lock_outline, size: 17),
                  'Pedido somente para consulta',
                  fontSize: 12,
                ),
              ),
            )
          else ...[
            Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: _alturaBotao,
                    child: OutlinedButton(
                      onPressed: _hasPendingItems ? onSendToKitchen : null,
                      child: _acaoDoBotao(
                        const Icon(Icons.outdoor_grill_outlined, size: 17),
                        'Enviar cozinha',
                        tecla: 'F9',
                        fontSize: 12,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: SizedBox(
                    height: _alturaBotao,
                    child: OutlinedButton(
                      onPressed: order != null && items.isNotEmpty && !printing
                          ? onPrint
                          : null,
                      child: _acaoDoBotao(
                        printing
                            ? const SizedBox(
                                width: 15,
                                height: 15,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.print_outlined, size: 17),
                        printing ? 'Gerando...' : 'Recibo',
                        tecla: printing ? null : 'F12',
                        fontSize: 12,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              height: _alturaBotao,
              child: FilledButton(
                // `order` pode ser nulo aqui: ir para o pagamento é um
                // dos dois gestos que FAZEM o pedido nascer. Exigir pedido
                // aberto deixaria o botão apagado justamente no rascunho, que
                // é quando ele mais precisa funcionar.
                onPressed: items.isNotEmpty ? onFinish : null,
                child: _acaoDoBotao(
                  const Icon(Icons.payments_outlined, size: 18),
                  'Ir para pagamento',
                  tecla: 'F4',
                ),
              ),
            ),
          ],
          if ('${order?['payment_status']}' == 'paid') ...[
            const SizedBox(height: 8),
            _invoiceAction(),
          ],
        ],
      ),
    );
  }

  /// A acao fiscal do pedido, conforme a situacao da nota.
  ///
  /// Nota autorizada nao se emite de novo: o que falta e o papel. Deixar o
  /// mesmo botao para os dois casos escondia isso do operador — e mandava a
  /// impressao passar pelo `/invoices/emit/`, que sem rede vira mais uma
  /// entrada na fila fiscal para uma nota que ja existe.
  Widget _invoiceAction() {
    final fiscal = order?['fiscal'] as Map<String, dynamic>?;
    final printable = fiscal?['printable'] == true;
    final state = '${fiscal?['fiscal_state'] ?? ''}';
    final busy = emittingInvoice;

    final label = switch (true) {
      _ when busy && printable => 'Imprimindo DANFE...',
      _ when busy => 'Emitindo NFC-e...',
      _ when printable => 'Imprimir DANFE',
      _ when state == 'rejected' || state == 'configuration_error' =>
        'Reenviar NFC-e',
      _ when state == 'processing' || state == 'reconciliation_required' =>
        'NFC-e aguardando a SEFAZ',
      _ when state == 'awaiting_transmission' => 'Transmitir NFC-e',
      _ => 'Emitir NFC-e',
    };
    // Enquanto a SEFAZ nao responde nao ha o que emitir nem o que imprimir:
    // insistir aqui so duplicaria consulta.
    final waiting = state == 'processing' || state == 'reconciliation_required';
    final action = printable ? onPrintInvoice : onEmitInvoice;

    return SizedBox(
      width: double.infinity,
      height: 44,
      child: OutlinedButton.icon(
        onPressed: busy || waiting ? null : action,
        icon: busy
            ? const SizedBox(
                width: 17,
                height: 17,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(
                printable ? Icons.print_outlined : Icons.receipt_long_outlined,
                size: 19,
              ),
        label: Text(label),
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

  Widget _empty(BuildContext context) {
    return AppEmptyState(
      icon: Icons.shopping_basket_outlined,
      title: 'O pedido está vazio',
      description: 'Selecione um produto ou pressione F2 para buscar.',
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
              child: CartItemCard(
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
              child: CartItemCard(
                item: item,
                money: money,
                canRemove: !_readOnly,
                onRemove: () => onVoidItem(item),
                selected: '${item['id']}' == selectedItemId,
                onTap: onSelectItem == null ? null : () => onSelectItem!(item),
                // Produto por peso não tem contador: a quantidade vem da
                // balança, e um `+1` ali seria um quilo a mais.
                onQuantityDelta:
                    _readOnly ||
                        onChangeQuantity == null ||
                        '${item['pricing_unit'] ?? 'unit'}' == 'kg'
                    ? null
                    : (delta) => onChangeQuantity!(item, delta),
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
              fontSize: 12,
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
