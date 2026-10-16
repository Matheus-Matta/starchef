import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../data/order_subject.dart';
import 'comanda_resumo.dart';
import 'order_formatters.dart';

/// Um cartão da grade inicial: o número grande, se está livre ou em uso, o
/// valor, a quantidade de itens e O QUE ela tem ("3x X-Burger · +2").
///
/// O número é o maior texto do cartão porque é o que o garçom procura com o
/// olho — é o que está escrito no cartão físico na mão dele.
class ComandaCard extends StatelessWidget {
  const ComandaCard({
    super.key,
    required this.command,
    required this.onTap,
    this.sending = 0,
    this.failed = 0,
  });

  final Map<String, dynamic> command;
  final VoidCallback onTap;

  /// Operações deste cartão ainda na fila do aparelho (subindo em segundo
  /// plano) e as que não saíram depois das tentativas.
  final int sending;
  final int failed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final itens = itemCountOf(command);
    // Consumo pendente é a fonte de verdade, não `status`: bases antigas
    // deixavam `occupied` num cartão já cobrado.
    final emUso = itens > 0;
    // O caixa está fechando a conta desta comanda agora: lançar aqui deixaria
    // o item fora do pagamento que ele está lendo para o cliente.
    final noCaixa = fieldText(command['closing_merge']).isNotEmpty;
    final (rotulo, cor) = noCaixa
        ? ('No caixa', AppColors.danger)
        : emUso
        ? ('Em uso', AppColors.warning)
        : ('Livre', AppColors.success);
    final mesa = fieldText(command['current_table_number']);
    final cliente = fieldText(command['customer_name']);
    final detalhe = [if (mesa.isNotEmpty) 'Mesa $mesa', ?_vazioNulo(cliente)];
    final resumo = resumoDaComanda(command['pending_preview']);

    return Material(
      color: scheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: AppTheme.radius,
        side: BorderSide(color: cor.withValues(alpha: emUso ? .55 : .25)),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: noCaixa ? null : onTap,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${command['number'] ?? ''}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  _Selo(texto: rotulo, cor: cor),
                ],
              ),
              const Spacer(),
              Text(
                emUso
                    ? '$itens ${itens == 1 ? 'item' : 'itens'} · '
                          '${money(command['pending_total'])}'
                    : 'Sem consumo',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              if (resumo.isNotEmpty)
                Text(
                  resumo,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 12, color: scheme.onSurface),
                ),
              const SizedBox(height: 2),
              Text(
                _fila() ?? (detalhe.isEmpty ? ' ' : detalhe.join(' · ')),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  color: failed > 0
                      ? AppColors.danger
                      : sending > 0
                      ? AppColors.warning
                      : scheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// O que este aparelho ainda deve ao servidor, quando deve — é o que
  /// importa mais ao garçom do que a mesa, logo depois de enviar.
  String? _fila() {
    if (failed > 0) return '$failed não enviado(s)';
    if (sending > 0) return 'Enviando…';
    return null;
  }

  static String? _vazioNulo(String texto) => texto.isEmpty ? null : texto;
}

class _Selo extends StatelessWidget {
  const _Selo({required this.texto, required this.cor});

  final String texto;
  final Color cor;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
    decoration: BoxDecoration(
      color: cor.withValues(alpha: .14),
      borderRadius: BorderRadius.circular(999),
    ),
    child: Text(
      texto,
      style: TextStyle(color: cor, fontSize: 11, fontWeight: FontWeight.w700),
    ),
  );
}
