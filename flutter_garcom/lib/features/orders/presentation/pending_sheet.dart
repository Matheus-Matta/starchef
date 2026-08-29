import 'package:flutter/material.dart';

import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';

/// Tudo que este aparelho ainda deve ao Caixa Principal, num lugar só.
///
/// Antes as pendências apareciam misturadas à lista de pedidos abertos, como
/// se fossem pedidos de verdade: o garçom não distinguia o que já estava no
/// caixa do que ainda era só uma intenção deste celular. Agora a lista de
/// pedidos mostra pedidos, e o que está a caminho (ou recusado) vive aqui,
/// atrás do contador no topo da tela.
Future<void> showPendingSheet(BuildContext context, RelayGateway gateway) =>
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: AnimatedBuilder(
          animation: gateway,
          builder: (context, _) => _PendingSheet(gateway: gateway),
        ),
      ),
    );

class _PendingSheet extends StatelessWidget {
  const _PendingSheet({required this.gateway});

  final RelayGateway gateway;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final pending = gateway.pending;
    final failed = gateway.failed;
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.of(context).size.height * .8,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
            child: Row(
              children: [
                const Expanded(
                  child: Text(
                    'Envios pendentes',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
                  ),
                ),
                if (pending.isNotEmpty)
                  TextButton.icon(
                    onPressed: gateway.flushing ? null : gateway.flushNow,
                    icon: const Icon(Icons.sync, size: 18),
                    label: const Text('Tentar agora'),
                  ),
              ],
            ),
          ),
          if (pending.isEmpty && failed.isEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
              child: Text(
                'Nada esperando. Tudo o que você lançou já está no Caixa '
                'Principal.',
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
            )
          else
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
                children: [
                  if (pending.isNotEmpty) ...[
                    _Label(
                      'A caminho do caixa (${pending.length})',
                      color: AppColors.warning,
                    ),
                    for (final mutation in pending)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(Icons.schedule_outlined),
                        title: Text(mutation.summary),
                        subtitle: Text(
                          mutation.attempts == 0
                              ? 'Esperando o Caixa Principal responder'
                              : '${mutation.attempts} tentativa(s) · '
                                    '${mutation.lastError ?? ''}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  if (failed.isNotEmpty) ...[
                    _Label(
                      'Nao aceitos pelo caixa (${failed.length})',
                      color: AppColors.danger,
                    ),
                    for (final failure in failed)
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: const Icon(
                          Icons.error_outline,
                          color: AppColors.danger,
                        ),
                        title: Text(failure.mutation.summary),
                        subtitle: Text(
                          failure.reason,
                          style: const TextStyle(color: AppColors.danger),
                        ),
                        trailing: Wrap(
                          spacing: 4,
                          children: [
                            IconButton(
                              tooltip: 'Reenviar',
                              onPressed: () => gateway.retryFailed(
                                failure.mutation.operationId,
                              ),
                              icon: const Icon(Icons.refresh),
                            ),
                            IconButton(
                              tooltip: 'Remover',
                              onPressed: () => gateway.discardFailed(
                                failure.mutation.operationId,
                              ),
                              icon: const Icon(Icons.delete_outline),
                            ),
                          ],
                        ),
                      ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text, {required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 10, bottom: 4),
    child: Text(
      text.toUpperCase(),
      style: TextStyle(
        fontSize: 12,
        fontWeight: FontWeight.w800,
        letterSpacing: .4,
        color: color,
      ),
    ),
  );
}
