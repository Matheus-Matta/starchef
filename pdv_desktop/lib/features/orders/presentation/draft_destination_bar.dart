import 'package:flutter/material.dart';

import 'draft_destination_parts.dart';

/// Para onde este rascunho vai — no topo do carrinho.
///
/// É um ATRIBUTO do pedido que está sendo montado, e fica na mesma altura em
/// que o operador confere o que vai cobrar. Antes esta escolha era uma tela
/// inteira ANTES do catálogo: o posto abria perguntando "qual o tipo de
/// atendimento?" e só depois mostrava os produtos.
///
/// Trocar de tela para responder isso custa caro no balcão, onde a resposta é
/// quase sempre a mesma — balcão —, e escolher "comanda" ali abria o cartão de
/// verdade. Aqui o padrão já está escolhido, e trocar é um toque sem ida ao
/// servidor: anexar e soltar comanda não falam com a rede.
class DraftDestinationBar extends StatelessWidget {
  const DraftDestinationBar({
    super.key,
    required this.orderType,
    required this.commands,
    required this.totalPorComanda,
    required this.table,
    required this.customer,
    required this.enabled,
    required this.onPickType,
    required this.onAttachCommand,
    required this.onDetachCommand,
  });

  final String orderType;

  /// Os cartões anexados, na ordem em que entraram. A mesa com quatro comandas
  /// que paga junto é o caso comum, não a exceção.
  final List<Map<String, dynamic>> commands;

  /// Quanto cada cartão já tem lançado, por id — o número que o cliente
  /// confere em voz alta antes de pagar.
  final Map<String, double> totalPorComanda;
  final Map<String, dynamic>? table;
  final Map<String, dynamic>? customer;
  final bool enabled;
  final ValueChanged<String> onPickType;
  final VoidCallback onAttachCommand;
  final ValueChanged<String> onDetachCommand;

  static const _tipos = [
    ('counter', 'Balcão', Icons.storefront_outlined),
    ('command', 'Comanda', Icons.qr_code_2_outlined),
    ('takeaway', 'Retirada', Icons.shopping_bag_outlined),
    ('delivery', 'Delivery', Icons.delivery_dining_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              for (final tipo in _tipos)
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 2),
                    child: DraftTypeTab(
                      rotulo: tipo.$2,
                      icone: tipo.$3,
                      ativo: orderType == tipo.$1,
                      onTap: enabled ? () => onPickType(tipo.$1) : null,
                    ),
                  ),
                ),
            ],
          ),
          if (orderType == 'command') ...[
            const SizedBox(height: 8),
            for (final comanda in commands)
              Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: DraftAttachedCommand(
                  command: comanda,
                  table: table,
                  total: totalPorComanda['${comanda['id']}'],
                  enabled: enabled,
                  onAttach: onAttachCommand,
                  onDetach: () => onDetachCommand('${comanda['id']}'),
                ),
              ),
            // O convite para o PRÓXIMO cartão fica sempre visível: é ele que
            // diz que dá para pagar várias comandas numa conta só. Escondido
            // atrás de um menu, ninguém descobre.
            DraftAttachedCommand(
              command: null,
              table: null,
              total: null,
              enabled: enabled,
              onAttach: onAttachCommand,
              onDetach: () {},
              rotuloVazio: commands.isEmpty
                  ? 'Anexar comanda'
                  : 'Anexar outra comanda',
            ),
          ] else if (customer != null) ...[
            const SizedBox(height: 8),
            Text(
              '${customer?['name'] ?? customer?['display_name'] ?? ''}',
              style: TextStyle(
                color: scheme.onSurfaceVariant,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
