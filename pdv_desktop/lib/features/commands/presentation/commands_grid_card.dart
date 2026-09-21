import 'package:flutter/material.dart';

import '../../../core/formatters/value_formatters.dart';
import '../../../core/theme/app_theme.dart';
import '../data/command_repository.dart';

/// Um cartão do SALÃO de comandas.
///
/// Fica em arquivo próprio porque é ele que carrega a regra de cor e o que o
/// operador lê de longe — e regra de cor é o que mais muda depois. Quem for
/// ajustar um matiz abre este arquivo e não precisa ler a busca nem a rolagem
/// da grade.
class CommandFloorCard extends StatelessWidget {
  const CommandFloorCard({
    super.key,
    required this.comanda,
    required this.onTap,
  });

  final Map<String, dynamic> comanda;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ocupada = comandaTemContaAberta(comanda);
    final cor = ocupada ? const Color(0xFFEA580C) : const Color(0xFF16A34A);
    final mesa = comanda['current_table_number'];
    final total = comanda['pending_total'];
    return Material(
      color: scheme.surface,
      borderRadius: AppTheme.radius,
      child: InkWell(
        onTap: onTap,
        borderRadius: AppTheme.radius,
        // O contorno é UNIFORME, e precisa continuar sendo: `Border` com um
        // lado de cor diferente é ilegal junto com `borderRadius`, e o Flutter
        // só descobre isso na hora de PINTAR — a caixa não pinta, os filhos não
        // aparecem, e o cartão fica desenhado e vazio na tela.
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            borderRadius: AppTheme.radius,
            border: Border.all(color: cor.withValues(alpha: .55)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${comanda['number'] ?? ''}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ),
                  Icon(Icons.circle, size: 10, color: cor),
                ],
              ),
              Text(
                '${comanda['code'] ?? ''}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 11),
              ),
              const Spacer(),
              // O valor pendente é o que o operador procura num salão cheio:
              // "qual mesa está pronta para fechar". Sem ele, cada cartão
              // precisaria ser aberto para descobrir.
              if (ocupada)
                Text(
                  ValueFormatters.money(total),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: cor,
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              Text(
                [
                  ocupada ? 'OCUPADA' : 'LIVRE',
                  if (mesa != null) 'Mesa $mesa',
                ].join(' · '),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: cor,
                  fontSize: 9,
                  fontWeight: FontWeight.w700,
                  letterSpacing: .4,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
