import 'dart:convert';

import 'package:flutter/material.dart';

import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_client.dart';
import '../../../core/widgets/copyable_error.dart';

/// Revisão das operações locais que ainda não chegaram ao servidor.
///
/// Antes o badge apenas informava "Revisar N": para saber o que estava preso
/// era preciso abrir o SQLite do terminal. Aqui o operador vê o que cada
/// pendência representa, o motivo da recusa, e decide entre tentar de novo ou
/// descartar — nada some sozinho.
class OutboxReviewDialog extends StatefulWidget {
  const OutboxReviewDialog({super.key, required this.api});

  final ApiClient api;

  static Future<void> show(BuildContext context, ApiClient api) =>
      showDialog<void>(
        context: context,
        builder: (_) => OutboxReviewDialog(api: api),
      );

  @override
  State<OutboxReviewDialog> createState() => _OutboxReviewDialogState();
}

class _OutboxReviewDialogState extends State<OutboxReviewDialog> {
  List<Map<String, dynamic>> operations = const [];
  bool loading = true;
  String? busyQueueId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => loading = true);
    final items = await widget.api.outboxOperations();
    if (!mounted) return;
    setState(() {
      operations = items;
      loading = false;
    });
  }

  Future<void> _retry(Map<String, dynamic> operation) async {
    final queueId = '${operation['queue_id']}';
    setState(() => busyQueueId = queueId);
    try {
      await widget.api.retryBlockedOperation(queueId);
      AppLogger.instance.info(
        'outbox_retry_requested',
        data: {'queue_id': queueId, 'path': operation['path']},
      );
      await _load();
    } finally {
      if (mounted) setState(() => busyQueueId = null);
    }
  }

  Future<void> _discard(Map<String, dynamic> operation) async {
    final confirmed = await _confirmDiscard(operation);
    if (confirmed != true || !mounted) return;
    final queueId = '${operation['queue_id']}';
    setState(() => busyQueueId = queueId);
    try {
      final removed = await widget.api.discardBlockedOperation(queueId);
      AppLogger.instance.warning(
        'outbox_discarded',
        data: {
          'queue_id': queueId,
          'path': operation['path'],
          'removed': removed,
          'body': operation['body'],
        },
      );
      if (!removed && mounted) {
        showAppError(
          context,
          'A operação saiu do estado bloqueado e voltou para a fila. '
          'Ela não foi descartada.',
          title: 'Descarte não aplicado',
        );
      }
      await _load();
    } finally {
      if (mounted) setState(() => busyQueueId = null);
    }
  }

  Future<bool?> _confirmDiscard(Map<String, dynamic> operation) =>
      showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Descartar esta operação?'),
          content: SizedBox(
            width: 440,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'A operação "${_describe(operation)}" será apagada deste '
                  'terminal e nunca chegará ao servidor.',
                ),
                const SizedBox(height: 10),
                const Text(
                  'Use isto apenas quando a venda já tiver sido lançada de '
                  'outra forma ou quando ela realmente não deve existir. '
                  'Se ela criou um pedido ou item local, as operações que '
                  'dependem dele também serão descartadas. O descarte fica '
                  'registrado no log.',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Manter na fila'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: Theme.of(dialogContext).colorScheme.error,
              ),
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Descartar'),
            ),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final blocked = operations
        .where((item) => item['state'] == 'blocked')
        .length;
    return AlertDialog(
      title: Row(
        children: [
          const Icon(Icons.sync_problem_outlined),
          const SizedBox(width: 10),
          const Expanded(child: Text('Operações aguardando o servidor')),
          IconButton(
            tooltip: 'Fechar',
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close),
          ),
        ],
      ),
      content: SizedBox(
        width: 760,
        height: 440,
        child: loading
            ? const Center(child: CircularProgressIndicator())
            : operations.isEmpty
            ? _empty(scheme)
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    blocked == 0
                        ? '${operations.length} operação(ões) na fila. Elas são '
                              'enviadas sozinhas quando o servidor responder.'
                        : '$blocked de ${operations.length} precisam de revisão '
                              'e não serão reenviadas automaticamente.',
                    style: TextStyle(color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView.separated(
                      itemCount: operations.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (_, index) =>
                          _tile(operations[index], scheme),
                    ),
                  ),
                ],
              ),
      ),
      actions: [
        TextButton.icon(
          onPressed: loading ? null : _load,
          icon: const Icon(Icons.refresh),
          label: const Text('Atualizar'),
        ),
        FilledButton.icon(
          onPressed:
              loading ||
                  (operations.isNotEmpty &&
                      operations.first['state'] == 'blocked')
              ? null
              : () async {
                  await widget.api.syncPendingNow();
                  await _load();
                },
          icon: const Icon(Icons.cloud_upload_outlined),
          label: const Text('Sincronizar agora'),
        ),
      ],
    );
  }

  Widget _empty(ColorScheme scheme) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.cloud_done_outlined, size: 54, color: scheme.primary),
        const SizedBox(height: 12),
        const Text(
          'Nenhuma operação pendente',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
        ),
        const SizedBox(height: 4),
        Text(
          'Tudo que foi registrado neste terminal já está no servidor.',
          style: TextStyle(color: scheme.onSurfaceVariant),
        ),
      ],
    ),
  );

  Widget _tile(Map<String, dynamic> operation, ColorScheme scheme) {
    final state = '${operation['state']}';
    final isBlocked = state == 'blocked';
    final queueId = '${operation['queue_id']}';
    final busy = busyQueueId == queueId;
    final attempts = operation['attempt_count'] as int? ?? 0;
    final error = '${operation['last_error'] ?? ''}'.trim();

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(vertical: 8),
      leading: Icon(
        isBlocked ? Icons.report_outlined : Icons.schedule_outlined,
        color: isBlocked ? scheme.error : scheme.onSurfaceVariant,
      ),
      title: Text(
        _describe(operation),
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            [
              _stateLabel(state),
              if (attempts > 0) '$attempts tentativa(s)',
              _createdAt(operation),
            ].where((part) => part.isNotEmpty).join(' · '),
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
          if (error.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                error,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 12,
                  color: isBlocked ? scheme.error : scheme.onSurfaceVariant,
                ),
              ),
            ),
        ],
      ),
      trailing: busy
          ? const SizedBox.square(
              dimension: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: 'Ver dados enviados',
                  onPressed: () => _showPayload(operation),
                  icon: const Icon(Icons.data_object),
                ),
                if (isBlocked) ...[
                  IconButton(
                    tooltip: 'Tentar novamente',
                    onPressed: () => _retry(operation),
                    icon: const Icon(Icons.refresh),
                  ),
                  IconButton(
                    tooltip: 'Descartar',
                    onPressed: () => _discard(operation),
                    icon: Icon(Icons.delete_outline, color: scheme.error),
                  ),
                ],
              ],
            ),
    );
  }

  void _showPayload(Map<String, dynamic> operation) {
    const encoder = JsonEncoder.withIndent('  ');
    final payload = encoder.convert({
      'method': operation['method'],
      'path': operation['path'],
      'query': operation['query'],
      'body': operation['body'],
      'idempotency_key': operation['idempotency_key'],
      'created_at': operation['created_at'],
      'last_error': operation['last_error'],
    });
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Row(
          children: [
            const Expanded(child: Text('Dados da operação')),
            IconButton(
              tooltip: 'Fechar',
              onPressed: () => Navigator.pop(dialogContext),
              icon: const Icon(Icons.close),
            ),
          ],
        ),
        content: SizedBox(
          width: 620,
          child: SingleChildScrollView(
            child: SelectableText(
              payload,
              style: const TextStyle(fontFamily: 'Consolas', fontSize: 12),
            ),
          ),
        ),
        actions: [
          TextButton.icon(
            onPressed: () => copyError(dialogContext, payload),
            icon: const Icon(Icons.copy_all_outlined),
            label: const Text('Copiar'),
          ),
        ],
      ),
    );
  }

  static String _stateLabel(String state) => switch (state) {
    'blocked' => 'Precisa de revisão',
    'retry' => 'Aguardando nova tentativa',
    _ => 'Na fila',
  };

  static String _createdAt(Map<String, dynamic> operation) {
    final created = DateTime.tryParse(
      '${operation['created_at'] ?? ''}',
    )?.toLocal();
    if (created == null) return '';
    String two(int value) => value.toString().padLeft(2, '0');
    return '${two(created.day)}/${two(created.month)} '
        '${two(created.hour)}:${two(created.minute)}';
  }

  /// Traduz método e rota para o que a operação significa para o operador.
  static String _describe(Map<String, dynamic> operation) {
    final method = '${operation['method']}';
    final path = '${operation['path']}';
    if (path == '/customers/' && method == 'POST') return 'Cadastro de cliente';
    if (path.startsWith('/customers/') && method == 'PATCH') {
      return 'Alteração de cliente';
    }
    if (path == '/orders/' && method == 'POST') return 'Novo pedido';
    if (path == '/orders/open-table/') return 'Abertura de pedido na mesa';
    if (path == '/orders/open-command/') return 'Abertura de pedido na comanda';
    if (RegExp(r'^/orders/[^/]+/items/$').hasMatch(path)) {
      final body = operation['body'];
      final quantity = body is Map ? body['quantity'] : null;
      return quantity == null
          ? 'Item adicionado ao pedido'
          : 'Item adicionado ao pedido (x$quantity)';
    }
    if (RegExp(r'^/orders/[^/]+/items/[^/]+/void/$').hasMatch(path)) {
      return 'Cancelamento de item';
    }
    if (RegExp(r'^/orders/[^/]+/send-to-kitchen/$').hasMatch(path)) {
      return 'Envio do pedido para a cozinha';
    }
    if (RegExp(r'^/orders/[^/]+/close/$').hasMatch(path)) {
      return 'Fechamento do pedido';
    }
    if (RegExp(r'^/orders/[^/]+/pay/$').hasMatch(path)) {
      return 'Pagamento do pedido';
    }
    return '$method $path';
  }
}
