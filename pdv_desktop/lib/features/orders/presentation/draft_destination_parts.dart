/// As duas peças da barra de destino: a aba e a comanda anexada.
///
/// Ficam em arquivo próprio porque a barra é uma COMPOSIÇÃO — quem for mexer
/// em como a aba se desenha não precisa reler a regra de quando cada peça
/// aparece, e vice-versa.
library;

import 'package:flutter/material.dart';

import '../../../core/formatters/value_formatters.dart';
import '../../../core/theme/app_theme.dart';

class DraftTypeTab extends StatelessWidget {
  const DraftTypeTab({
    super.key,
    required this.rotulo,
    required this.icone,
    required this.ativo,
    required this.onTap,
  });

  final String rotulo;
  final IconData icone;
  final bool ativo;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final cor = ativo ? scheme.primary : scheme.onSurfaceVariant;
    return Material(
      color: ativo ? scheme.primaryContainer : Colors.transparent,
      borderRadius: AppTheme.radius,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppTheme.radius,
        child: Container(
          height: 46,
          decoration: BoxDecoration(
            borderRadius: AppTheme.radius,
            border: Border.all(
              color: ativo ? scheme.primary : scheme.outlineVariant,
            ),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icone, size: 16, color: cor),
              const SizedBox(height: 2),
              Text(
                rotulo,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: cor,
                  fontSize: 10,
                  fontWeight: ativo ? FontWeight.w800 : FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A comanda anexada, ou o convite para anexar uma.
class DraftAttachedCommand extends StatelessWidget {
  const DraftAttachedCommand({
    super.key,
    required this.command,
    required this.table,
    required this.enabled,
    required this.onAttach,
    required this.onDetach,
    this.total,
    this.rotuloVazio = 'Anexar comanda',
  });

  final Map<String, dynamic>? command;
  final Map<String, dynamic>? table;

  /// Quanto este cartão já tem lançado. Nulo enquanto a conta dele não chegou
  /// do servidor — e aí não se mostra número nenhum, porque um zero no lugar
  /// de "ainda carregando" é o operador cobrando a menos.
  final double? total;
  final String rotuloVazio;
  final bool enabled;
  final VoidCallback onAttach;
  final VoidCallback onDetach;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (command == null) {
      return OutlinedButton.icon(
        onPressed: enabled ? onAttach : null,
        icon: const Icon(Icons.add_card_outlined, size: 17),
        label: Text(rotuloVazio),
      );
    }
    final mesa = table?['number'] ?? command?['current_table_number'];
    return Container(
      padding: const EdgeInsets.fromLTRB(11, 7, 5, 7),
      decoration: BoxDecoration(
        borderRadius: AppTheme.radius,
        color: scheme.primaryContainer,
      ),
      child: Row(
        children: [
          Icon(Icons.qr_code_2_rounded, size: 17, color: scheme.primary),
          const SizedBox(width: 7),
          Expanded(
            child: Text(
              [
                'Comanda ${command?['number'] ?? ''}',
                if (mesa != null) 'Mesa $mesa',
              ].join(' · '),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: scheme.primary,
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          if (total != null)
            Text(
              ValueFormatters.money(total),
              style: TextStyle(
                color: scheme.primary,
                fontSize: 12,
                fontWeight: FontWeight.w800,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          // Soltar não desfaz nada no servidor, porque nada foi feito nele: é
          // só tirar o cartão deste rascunho.
          IconButton(
            onPressed: enabled ? onDetach : null,
            icon: const Icon(Icons.close_rounded, size: 17),
            tooltip: 'Soltar comanda',
            visualDensity: VisualDensity.compact,
          ),
        ],
      ),
    );
  }
}
