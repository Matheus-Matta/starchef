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
    this.onFinish,
    required this.onSendToKitchen,
    required this.onPrint,
    this.onCancel,
    this.onEmitInvoice,
    this.onPrintInvoice,
    required this.printing,
    this.emittingInvoice = false,
    this.selectedItemId,
    this.onSelectItem,
    this.onChangeQuantity,
  });

  final Map<String, dynamic>? order;
  final Map<String, dynamic>? table;
  final Map<String, dynamic>? command;
  final Map<String, dynamic>? customer;
  final List<Map<String, dynamic>> items;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onVoidItem;

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
  static const _alturaBotao = 38.0;

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
            // Sem pedido não há tipo, nem pendência, nem ação: a faixa some
            // em vez de aparecer vazia com um "BALCÃO" que não quer dizer nada.
            if (order != null) ...[
              _header(context),
              Divider(height: 1, color: scheme.outlineVariant),
            ],
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

  /// O que sobrou do cabeçalho: tipo, aviso de pendência e o menu.
  ///
  /// O número do pedido, o contexto (comanda, mesa, cliente) e o ícone saíram
  /// daqui e foram para a BARRA DO APLICATIVO. Eram a mesma informação que a
  /// barra já mostrava logo acima, repetida em corpo maior, ocupando a
  /// primeira faixa do painel — o lugar onde deveria começar a lista de itens.
  Widget _header(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pendingOffline = order?['_offline_pending'] == true;
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 6, 6, 6),
      child: Row(
        children: [
          ShadBadge.outline(
            shape: const RoundedRectangleBorder(borderRadius: AppTheme.radius),
            padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
            child: Text(
              _typeLabel('${order?['order_type'] ?? ''}').toUpperCase(),
              style: const TextStyle(fontSize: 8, fontWeight: FontWeight.w900),
            ),
          ),
          const Spacer(),
          if (pendingOffline)
            Tooltip(
              message: 'Pedido salvo localmente e aguardando sincronização.',
              child: ShadBadge.secondary(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                backgroundColor: scheme.tertiaryContainer,
                shape: const RoundedRectangleBorder(
                  borderRadius: AppTheme.radius,
                ),
                child: const Text(
                  'LOCAL',
                  style: TextStyle(fontSize: 8, fontWeight: FontWeight.w900),
                ),
              ),
            ),
          // O menu aparece para qualquer operador; o que a permissão controla é
          // se o item DENTRO dele funciona.
          //
          // Antes o menu inteiro sumia quando faltava `orders.cancel`, e com
          // ele sumia a única pista de que cancelar um pedido é possível: o
          // operador concluía que o PDV não faz isso, em vez de saber que
          // precisa chamar alguém que pode. Desabilitado, ele diz o que existe
          // e por que está fora de alcance — sem afrouxar nada, porque quem
          // não tem a permissão continua sem cancelar.
          if (order != null && !_readOnly)
            PopupMenuButton<String>(
              tooltip: 'Mais ações do pedido',
              icon: const Icon(Icons.more_vert),
              onSelected: (_) => onCancel?.call(),
              itemBuilder: (context) => [
                PopupMenuItem(
                  value: 'cancel',
                  enabled: onCancel != null,
                  child: _cancelEntry(scheme, allowed: onCancel != null),
                ),
              ],
            ),
        ],
      ),
    );
  }

  /// "Cancelar pedido" — em vermelho quando é possível, apagado e explicado
  /// quando o operador não tem `orders.cancel`.
  Widget _cancelEntry(ColorScheme scheme, {required bool allowed}) {
    final color = allowed ? scheme.error : scheme.onSurfaceVariant;
    return Row(
      children: [
        Icon(Icons.cancel_outlined, size: 18, color: color),
        const SizedBox(width: 9),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Cancelar pedido',
              style: TextStyle(color: color, fontWeight: FontWeight.w700),
            ),
            if (!allowed)
              Text(
                'Seu perfil não tem permissão',
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 11),
              ),
          ],
        ),
      ],
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
          const SizedBox(height: 10),
          // AS DUAS AÇÕES DO PEDIDO ABERTO, LADO A LADO E DO MESMO TAMANHO.
          //
          // Antes havia um botão só, "Revisar pedido", que abria um diálogo de
          // onde saíam os dois caminhos: mandar para a produção e ir para o
          // pagamento. Mandar comida para a cozinha passava por uma tela que
          // fala de dinheiro, e quem não sabia disso usava F9 — ou não usava.
          // Agora cada caminho é um botão, e o diálogo do pagamento pergunta
          // só o que ainda precisa ser decidido: a taxa de serviço.
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
          else
            Row(
              children: [
                Expanded(
                  child: SizedBox(
                    height: _alturaBotao,
                    child: OutlinedButton(
                      onPressed: _hasPendingItems ? onSendToKitchen : null,
                      child: _acaoDoBotao(
                        const Icon(Icons.outdoor_grill_outlined, size: 17),
                        'Enviar pedidos',
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
                    child: FilledButton(
                      onPressed: order != null && items.isNotEmpty
                          ? onFinish
                          : null,
                      child: _acaoDoBotao(
                        const Icon(Icons.payments_outlined, size: 17),
                        'Pagamento',
                        tecla: 'F10',
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
            child: OutlinedButton(
              onPressed: order != null && items.isNotEmpty && !printing
                  ? onPrint
                  : null,
              child: _acaoDoBotao(
                printing
                    ? const SizedBox(
                        width: 15,
                        height: 15,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.print_outlined, size: 17),
                printing ? 'Gerando recibo...' : 'Imprimir recibo',
                tecla: printing ? null : 'F12',
                fontSize: 12,
              ),
            ),
          ),
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
class _CartItem extends StatelessWidget {
  const _CartItem({
    required this.item,
    required this.canRemove,
    required this.money,
    required this.onRemove,
    this.selected = false,
    this.onTap,
    this.onQuantityDelta,
  });

  final Map<String, dynamic> item;
  final bool canRemove;
  final String Function(dynamic) money;
  final VoidCallback onRemove;
  final bool selected;
  final VoidCallback? onTap;

  /// Contador de unidades. `null` esconde os botões — item já em produção,
  /// pedido fechado ou produto vendido por peso.
  final ValueChanged<int>? onQuantityDelta;

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
                      fontSize: 12,
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
                      fontSize: 12,
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
                ] else if (onQuantityDelta != null) ...[
                  const SizedBox(height: 6),
                  _quantityStepper(context),
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
                  fontSize: 12,
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

  /// `‹ 3 ›` embaixo do nome, para o item ainda não enviado.
  Widget _quantityStepper(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final quantity = OrderCartPanel._number(item['quantity']);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _stepperButton(
          context,
          icon: Icons.remove_rounded,
          // Um a menos que 1 é zero, e zero é cancelar — o mesmo caminho do
          // "×", com motivo e registro. O botão não some nessa hora: sumir
          // faria o operador procurar outro jeito de tirar o item.
          tooltip: quantity <= 1 ? 'Cancelar item' : 'Uma unidade a menos',
          onPressed: () => onQuantityDelta!(-1),
        ),
        SizedBox(
          width: 34,
          child: Text(
            quantity.toStringAsFixed(0),
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w900),
          ),
        ),
        _stepperButton(
          context,
          icon: Icons.add_rounded,
          tooltip: 'Uma unidade a mais',
          onPressed: () => onQuantityDelta!(1),
        ),
        const SizedBox(width: 4),
        Text(
          'un',
          style: TextStyle(
            color: scheme.onSurfaceVariant,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }

  Widget _stepperButton(
    BuildContext context, {
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: InkResponse(
        onTap: onPressed,
        radius: 17,
        child: Container(
          width: 26,
          height: 26,
          decoration: BoxDecoration(
            border: Border.all(color: scheme.outlineVariant),
            borderRadius: BorderRadius.circular(7),
          ),
          child: Icon(icon, size: 15, color: scheme.onSurface),
        ),
      ),
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
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w800),
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
