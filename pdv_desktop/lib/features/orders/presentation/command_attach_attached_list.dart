import 'package:flutter/material.dart';

import 'draft_attached_command_row.dart';

/// O bloco "NESTA CONTA": os cartões que já entraram, cada um com o seu X.
///
/// Fica ACIMA da lista de onde eles saíram porque tirar é o inverso exato de
/// pôr, e os dois gestos precisam ficar no mesmo lugar. Some inteiro quando
/// não há nenhum — um rótulo sobre o vazio só ocupa a altura que a lista de
/// baixo precisa.
class CommandAttachAttachedList extends StatelessWidget {
  const CommandAttachAttachedList({
    super.key,
    required this.attached,
    required this.totals,
    required this.onDetach,
  });

  final List<Map<String, dynamic>> attached;
  final Map<String, num> totals;
  final ValueChanged<String> onDetach;

  @override
  Widget build(BuildContext context) {
    if (attached.isEmpty) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'NESTA CONTA',
          style: TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.4,
            color: scheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 6),
        for (final comanda in attached)
          Padding(
            padding: const EdgeInsets.only(bottom: 5),
            child: DraftAttachedCommandRow(
              command: comanda,
              total: totals['${comanda['id']}'],
              onDetach: () => onDetach('${comanda['id']}'),
            ),
          ),
        const SizedBox(height: 10),
        Divider(height: 1, color: scheme.outlineVariant),
        const SizedBox(height: 10),
      ],
    );
  }
}
