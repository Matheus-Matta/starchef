import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';

/// Uma comanda sentada NESTA mesa, na tela da mesa.
///
/// O X fica na própria linha, ao lado do que ele tira — e não num menu ou numa
/// segunda tela. Tirar um cartão da mesa é o inverso exato de sentá-lo, e é o
/// que se faz quando o cliente troca de lugar ou o cartão foi bipado errado.
///
/// Abrir o cartão continua sendo o toque na linha: é o gesto mais comum, e
/// ficaria estranho exigir um alvo menor para ele do que para o X.
class TableCommandRow extends StatelessWidget {
  const TableCommandRow({
    super.key,
    required this.command,
    required this.onOpen,
    this.onUnlink,
  });

  final Map<String, dynamic> command;
  final VoidCallback onOpen;

  /// Nulo quando a tela não pode desvincular — por exemplo enquanto uma
  /// chamada anterior ainda está no ar.
  final VoidCallback? onUnlink;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final nome = '${command['customer_name'] ?? ''}'.trim();
    return ShadCard(
      padding: EdgeInsets.zero,
      radius: AppTheme.radius,
      shadows: const [],
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      child: Material(
        type: MaterialType.transparency,
        child: ListTile(
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 8,
          ),
          leading: CircleAvatar(
            backgroundColor: scheme.primaryContainer,
            child: Text(
              '${command['number']}',
              style: TextStyle(
                color: scheme.onPrimaryContainer,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          title: Text(
            nome.isEmpty ? 'Comanda ${command['number']}' : nome,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          subtitle: Text(
            '${command['code'] ?? 'Sem código'}',
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
          onTap: onOpen,
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                onPressed: onUnlink,
                icon: const Icon(Icons.close, size: 18),
                tooltip: 'Tirar a comanda ${command['number']} desta mesa',
                visualDensity: VisualDensity.compact,
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}
