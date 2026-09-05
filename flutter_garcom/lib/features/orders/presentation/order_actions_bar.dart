import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';
import 'order_formatters.dart';

/// A barra de baixo do pedido: quanto deu, quanto já entrou e o que fazer.
class OrderActionsBar extends StatelessWidget {
  const OrderActionsBar({
    super.key,
    required this.total,
    required this.paid,
    required this.pending,
    required this.drafts,
    required this.busy,
    required this.queued,
    required this.onAdd,
    required this.onSend,
    required this.onReceive,
  });

  final Object? total;

  /// Já recebido, somando o que o Caixa Principal confirmou.
  final double paid;

  /// Tudo que ainda vai para a cozinha.
  final int pending;

  /// Itens escolhidos e ainda não enviados: é o que o botão de confirmar vai
  /// mandar, e o número que o garçom confere antes de tocar.
  final int drafts;

  final bool busy;

  /// O envio à cozinha já está na fila offline, esperando o caixa responder.
  final bool queued;

  final VoidCallback onAdd;
  final VoidCallback? onSend;

  /// Receber pagamento: o aparelho operando como caixa secundário. `null`
  /// quando o pedido ainda não foi fechado (isso só acontece no caixa).
  final VoidCallback? onReceive;

  @override
  Widget build(BuildContext context) => AppBottomBar(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _Line(label: 'Total', value: money(total), strong: true),
        if (paid > 0) ...[
          const SizedBox(height: 2),
          _Line(label: 'Recebido', value: money(paid)),
        ],
        const SizedBox(height: AppTheme.gap),
        Row(
          children: [
            Expanded(
              child: ShadButton.outline(
                onPressed: busy ? null : onAdd,
                height: AppTheme.controlHeight,
                leading: const Icon(Icons.add, size: 18),
                child: const Text('Adicionar item'),
              ),
            ),
            const SizedBox(width: AppTheme.gap),
            Expanded(
              child: ShadButton(
                onPressed: busy ? null : onSend,
                enabled: !busy && onSend != null,
                height: AppTheme.controlHeight,
                leading: (busy || queued)
                    ? const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white,
                        ),
                      )
                    : const Icon(Icons.send, size: 18),
                child: Text(_sendLabel),
              ),
            ),
          ],
        ),
        if (onReceive != null) ...[
          const SizedBox(height: AppTheme.gap),
          ShadButton.secondary(
            onPressed: busy ? null : onReceive,
            enabled: !busy,
            height: AppTheme.controlHeight,
            leading: const Icon(Icons.payments_outlined, size: 18),
            child: const Text('Receber'),
          ),
        ],
      ],
    ),
  );

  /// O rótulo diz o que vai acontecer AGORA: com item escolhido e não enviado,
  /// o toque manda tudo e pede a impressão da comanda.
  String get _sendLabel {
    if (queued) return 'Aguardando conexão';
    if (drafts > 0) return 'Enviar e imprimir ($drafts)';
    if (pending > 0) return 'Enviar ($pending)';
    return 'Tudo enviado';
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.label, required this.value, this.strong = false});

  final String label;
  final String value;
  final bool strong;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Text(
        label,
        style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
      ),
      const Spacer(),
      Text(
        value,
        style: strong
            ? const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)
            : null,
      ),
    ],
  );
}
