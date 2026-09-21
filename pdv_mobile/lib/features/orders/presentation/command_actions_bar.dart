import 'package:flutter/material.dart';

import 'order_formatters.dart';

/// A barra do cartão aberto: quanto há pendente, e os dois gestos do garçom.
///
/// **Não tem pagamento**, ao contrário da barra do pedido. A comanda anota e
/// manda para a produção; cobrar é gesto do caixa — e um botão de pagamento
/// aqui convidaria o garçom a fechar a conta de uma mesa que ainda come.
class CommandActionsBar extends StatelessWidget {
  const CommandActionsBar({
    super.key,
    required this.total,
    required this.busy,
    required this.canSend,
    required this.onAdd,
    required this.onSend,
  });

  final double total;
  final bool busy;

  /// Há item que ainda NÃO foi para a produção. Reenviar o que a cozinha já
  /// recebeu faria o prato sair duas vezes.
  final bool canSend;
  final VoidCallback onAdd;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(12),
    child: Row(
      children: [
        Expanded(
          child: Text(
            'Pendente  ${money(total)}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ),
        TextButton.icon(
          onPressed: busy ? null : onAdd,
          icon: const Icon(Icons.add, size: 18),
          label: const Text('Item'),
        ),
        const SizedBox(width: 6),
        FilledButton.icon(
          onPressed: busy || !canSend ? null : onSend,
          icon: const Icon(Icons.outdoor_grill_outlined, size: 18),
          label: const Text('Cozinha'),
        ),
      ],
    ),
  );
}
