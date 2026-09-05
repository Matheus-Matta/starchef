import 'package:flutter/material.dart';

import '../../../core/relay/pending_mutation.dart';
import '../../../core/relay/relay_gateway.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/shadcn_layout.dart';

/// Tudo que este aparelho ainda deve ao Caixa Principal, num lugar só.
///
/// Antes as pendências apareciam misturadas à lista de pedidos abertos, como
/// se fossem pedidos de verdade: o garçom não distinguia o que já estava no
/// caixa do que ainda era só uma intenção deste celular. Agora a lista de
/// pedidos mostra pedidos, e o que está a caminho (ou recusado) vive aqui,
/// atrás do contador no topo da tela.
///
/// É a ÚNICA folha de pendências do app. A faixa de recusas ([SyncBanner])
/// abria uma segunda folha, quase igual, que listava só as recusadas — duas
/// telas para o mesmo assunto, cada uma com um verbo diferente para o mesmo
/// botão ("Descartar" numa, "Remover" na outra).
Future<void> showPendingSheet(BuildContext context, RelayGateway gateway) =>
    showAppSheet<void>(
      context,
      builder: (context) => AnimatedBuilder(
        animation: gateway,
        builder: (context, _) => _PendingSheet(gateway: gateway),
      ),
    );

class _PendingSheet extends StatelessWidget {
  const _PendingSheet({required this.gateway});

  final RelayGateway gateway;

  @override
  Widget build(BuildContext context) {
    final pending = gateway.pending;
    final failed = gateway.failed;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppSheetHeader(
          title: 'Envios pendentes',
          trailing: pending.isEmpty
              ? null
              : TextButton.icon(
                  onPressed: gateway.flushing ? null : gateway.flushNow,
                  icon: const Icon(Icons.sync, size: 18),
                  label: const Text('Tentar agora'),
                ),
        ),
        if (pending.isEmpty && failed.isEmpty)
          const AppEmptyState(
            icon: Icons.cloud_done_outlined,
            title: 'Nada esperando',
            description: 'Tudo o que você lançou já está no Caixa Principal.',
          )
        else
          Flexible(
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
              children: [
                if (pending.isNotEmpty) ...[
                  AppSectionLabel(
                    label: 'A caminho do caixa (${pending.length})',
                    color: AppColors.warning,
                  ),
                  for (final mutation in pending)
                    _PendingRow(mutation: mutation),
                ],
                if (failed.isNotEmpty) ...[
                  AppSectionLabel(
                    label: 'Não aceitos pelo caixa (${failed.length})',
                    color: AppColors.danger,
                  ),
                  for (final failure in failed)
                    _FailedRow(failure: failure, gateway: gateway),
                ],
              ],
            ),
          ),
      ],
    );
  }
}

class _PendingRow extends StatelessWidget {
  const _PendingRow({required this.mutation});

  final PendingMutation mutation;

  @override
  Widget build(BuildContext context) => ListTile(
    contentPadding: EdgeInsets.zero,
    leading: const Icon(Icons.schedule_outlined),
    title: Text(mutation.summary),
    subtitle: Text(
      mutation.attempts == 0
          ? 'Esperando o Caixa Principal responder'
          : '${mutation.attempts} tentativa(s) · ${mutation.lastError ?? ''}',
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
    ),
  );
}

class _FailedRow extends StatelessWidget {
  const _FailedRow({required this.failure, required this.gateway});

  final FailedMutation failure;
  final RelayGateway gateway;

  @override
  Widget build(BuildContext context) {
    final operationId = failure.mutation.operationId;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.error_outline, color: AppColors.danger),
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
            onPressed: () => gateway.retryFailed(operationId),
            icon: const Icon(Icons.refresh),
          ),
          IconButton(
            tooltip: 'Remover',
            onPressed: () => gateway.discardFailed(operationId),
            icon: const Icon(Icons.delete_outline),
          ),
        ],
      ),
    );
  }
}
