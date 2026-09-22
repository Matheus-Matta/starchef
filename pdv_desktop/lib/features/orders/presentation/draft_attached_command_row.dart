import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Um cartão JÁ anexado, com o X que o tira da conta.
///
/// Mora no topo do diálogo de comandas, logo acima da lista de onde ele saiu:
/// tirar é o inverso exato de pôr, e os dois gestos precisam ficar no mesmo
/// lugar. Antes esta linha ficava empilhada fora, acima do botão de anexar, e
/// numa mesa com quatro cartões o carrinho começava com quatro linhas antes do
/// primeiro produto.
///
/// O valor fica ao lado do número porque é o que o cliente confere em voz alta
/// antes de pagar: numa conta com quatro cartões, "quanto é a minha?" é a
/// primeira pergunta.
class DraftAttachedCommandRow extends StatelessWidget {
  const DraftAttachedCommandRow({
    super.key,
    required this.command,
    required this.onDetach,
    this.total,
    this.enabled = true,
  });

  final Map<String, dynamic> command;
  final VoidCallback onDetach;
  final num? total;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final mesa = command['current_table_number'];
    return Container(
      padding: const EdgeInsets.fromLTRB(10, 6, 6, 6),
      decoration: BoxDecoration(
        color: scheme.primaryContainer.withValues(alpha: .35),
        border: Border.all(color: scheme.primary.withValues(alpha: .45)),
        borderRadius: AppTheme.radius,
      ),
      child: Row(
        children: [
          Icon(Icons.qr_code_2_outlined, size: 17, color: scheme.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              mesa == null
                  ? 'Comanda ${command['number']}'
                  : 'Comanda ${command['number']} · Mesa $mesa',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
            ),
          ),
          if (total != null) ...[
            Text(
              _dinheiro(total!),
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: scheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(width: 4),
          ],
          IconButton(
            onPressed: enabled ? onDetach : null,
            icon: const Icon(Icons.close, size: 17),
            tooltip: 'Retirar comanda ${command['number']}',
            visualDensity: VisualDensity.compact,
            constraints: const BoxConstraints.tightFor(width: 30, height: 30),
            padding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }

  static String _dinheiro(num valor) =>
      'R\$ ${valor.toStringAsFixed(2).replaceAll('.', ',')}';
}
