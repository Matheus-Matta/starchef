import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/data/order_item_status.dart';
import '../../../core/theme/app_theme.dart';
import 'cart_command_badge.dart';
import 'cart_item_labels.dart';
import 'cart_item_status_chip.dart';
import 'cart_quantity_stepper.dart';

/// UMA LINHA DO CARRINHO, e a mesma nas duas telas.
///
/// Venda e comanda mostram a mesma coisa — produto, variações, observação,
/// quantidade e valor — e mostravam de jeitos diferentes: a comanda tinha
/// linha própria, sem contador e sem o desenho do cartão. Quem alterna entre
/// as duas no turno reaprendia a ler a mesma informação.
///
/// Imagem do produto fica de fora nas duas: ela ajuda a ESCOLHER, e aqui a
/// escolha já foi feita.
class CartItemCard extends StatelessWidget {
  const CartItemCard({
    super.key,
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

  /// Item de COMANDA não se apaga aqui: ele não é deste carrinho, é uma
  /// anotação que já existe no cartão. Um X daria a impressão de apagar o
  /// consumo — o caminho certo é retirar a comanda inteira, no diálogo.
  bool get _podeRemover => canRemove && numeroDaComandaDoItem(item) == null;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final note = '${item['customer_note'] ?? ''}'.trim();
    final extras = extrasDoItem(item);
    // Riscado = fora da conta. Valia só para a cortesia; o item CANCELADO
    // aparecia com o preço em negrito igual aos que somam, e a única pista de
    // que ele saiu era a etiqueta de status. Quem confere a conta na tela lê o
    // valor, não a etiqueta.
    final outOfBill = OrderItemStatus.isOutOfBill(item);

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
                if (numeroDaComandaDoItem(item) case final numero?) ...[
                  const SizedBox(height: 3),
                  CartCommandBadge(numero: numero),
                ],
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
                  CartItemStatusChip(
                        status: '${item['status'] ?? ''}',
                        batchNumber: item['batch_number'],
                      ),
                ] else if (onQuantityDelta != null) ...[
                  const SizedBox(height: 6),
                  CartQuantityStepper(quantity: item['quantity'], onDelta: onQuantityDelta!),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${rotuloDeQuantidade(item)} ${money(item['unit_price'])}'
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
                  fontFeatures: const [FontFeature.tabularFigures()],
                  decoration: outOfBill ? TextDecoration.lineThrough : null,
                  color: outOfBill ? scheme.onSurfaceVariant : null,
                ),
              ),
            ],
          ),
          if (_podeRemover)
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
}
