import 'package:flutter/material.dart';

import '../../../core/data/print_queue_service.dart';
import '../../../core/errors/app_error.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/widgets/app_dialog.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../../core/widgets/shadcn_layout.dart';
import '../services/local_device_agent.dart';

/// Os cupons que ainda não saíram no papel, e o que fazer com eles.
///
/// A fila de impressão é durável de propósito: um cupom que falhou por falta
/// de papel espera e sai quando a impressora volta. O efeito colateral era não
/// haver nenhum lugar para ver o que está esperando — "não imprimiu e não deu
/// erro" só se investigava abrindo o SQLite do terminal, e não havia como
/// desistir de um cupom que não interessa mais.
class PrintQueueDialog extends StatefulWidget {
  const PrintQueueDialog({super.key, required this.agent});

  final LocalDeviceAgent agent;

  static Future<void> show(BuildContext context, LocalDeviceAgent agent) =>
      showDialog<void>(
        context: context,
        builder: (_) => PrintQueueDialog(agent: agent),
      );

  @override
  State<PrintQueueDialog> createState() => _PrintQueueDialogState();
}

class _PrintQueueDialogState extends State<PrintQueueDialog> {
  List<PrintQueueEntry> entries = const [];
  bool loading = true;
  int? busyEntryId;

  PrintQueueService? get _queue => widget.agent.printQueue;
  String? get _scope => widget.agent.printScope;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final queue = _queue;
    final scope = _scope;
    if (queue == null || scope == null) {
      setState(() {
        entries = const [];
        loading = false;
      });
      return;
    }
    setState(() => loading = true);
    final rows = await queue.entries(scope: scope);
    if (!mounted) return;
    setState(() {
      entries = rows;
      loading = false;
    });
  }

  /// Recoloca o cupom na frente da fila e drena agora.
  ///
  /// Drenar aqui é o ponto: sem isso, "tentar agora" só mexeria numa coluna do
  /// banco e o operador ficaria esperando o próximo ciclo de vinte segundos
  /// sem entender por que nada aconteceu.
  Future<void> _retry(PrintQueueEntry entry) async {
    final queue = _queue;
    if (queue == null) return;
    setState(() => busyEntryId = entry.id);
    try {
      await queue.retryNow(entry.id);
      AppLogger.instance.info(
        'print_queue_retry_manual',
        data: {'job_id': entry.jobId, 'job_type': entry.jobType},
      );
      await widget.agent.drainPrintQueue();
      await _load();
    } finally {
      if (mounted) setState(() => busyEntryId = null);
    }
  }

  Future<void> _retryAll() async {
    final queue = _queue;
    final scope = _scope;
    if (queue == null || scope == null) return;
    setState(() => loading = true);
    for (final entry in entries) {
      await queue.retryNow(entry.id);
    }
    AppLogger.instance.info(
      'print_queue_retry_todos',
      data: {'total': entries.length},
    );
    await widget.agent.drainPrintQueue();
    await _load();
  }

  /// Esvazia a fila inteira.
  ///
  /// Descartar um a um não é uma opção com trinta cupons esperando e fila no
  /// balcão — que é exatamente o estado em que um terminal fica depois de
  /// herdar trabalho que não era dele.
  Future<void> _clearAll() async {
    final total = entries.length;
    final confirmed = await _confirmClearAll(total);
    if (confirmed != true || !mounted) return;
    final queue = _queue;
    final scope = _scope;
    if (queue == null || scope == null) return;
    setState(() => loading = true);
    final removed = await queue.clearPending(scope: scope);
    AppLogger.instance.warning(
      'print_queue_esvaziada',
      data: {'descartados': removed},
    );
    await _load();
    if (!mounted) return;
    showAppToast(
      context,
      removed == 1
          ? '1 cupom saiu da fila e não será impresso.'
          : '$removed cupons saíram da fila e não serão impressos.',
      severity: AppErrorSeverity.warning,
    );
  }

  Future<bool?> _confirmClearAll(int total) => showDialog<bool>(
    context: context,
    builder: (dialogContext) => AppDialog(
      title: const Text('Limpar a fila de impressão?'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              total == 1
                  ? 'O cupom que está esperando sai da fila e não será '
                        'impresso.'
                  : 'Os $total cupons que estão esperando saem da fila e não '
                        'serão impressos.',
            ),
            const SizedBox(height: 10),
            const Text(
              'Nenhuma venda é alterada — só o papel deixa de sair. Não dá '
              'para desfazer: o que for descartado aqui precisa ser '
              'reimpresso pelo caixa, um a um. O descarte fica registrado '
              'no log.',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(dialogContext, false),
          child: const Text('Manter a fila'),
        ),
        FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: Theme.of(dialogContext).colorScheme.error,
          ),
          onPressed: () => Navigator.pop(dialogContext, true),
          child: const Text('Limpar tudo'),
        ),
      ],
    ),
  );

  Future<void> _discard(PrintQueueEntry entry) async {
    final confirmed = await _confirmDiscard(entry);
    if (confirmed != true || !mounted) return;
    final queue = _queue;
    if (queue == null) return;
    setState(() => busyEntryId = entry.id);
    try {
      await queue.discard(entry.id);
      AppLogger.instance.warning(
        'print_queue_descartado',
        data: {
          'job_id': entry.jobId,
          'job_type': entry.jobType,
          'tentativas': entry.attempts,
          'ultimo_erro': entry.lastError,
        },
      );
      await _load();
    } finally {
      if (mounted) setState(() => busyEntryId = null);
    }
  }

  Future<bool?> _confirmDiscard(PrintQueueEntry entry) => showDialog<bool>(
    context: context,
    builder: (dialogContext) => AppDialog(
      title: const Text('Descartar este cupom?'),
      content: SizedBox(
        width: 440,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '"${_title(entry)}" sai da fila e não será impresso.',
            ),
            const SizedBox(height: 10),
            const Text(
              'A venda não é alterada — só o papel deixa de sair. Use quando '
              'o cupom já foi impresso de outra forma ou não interessa mais. '
              'O descarte fica registrado no log.',
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
    final failed = entries
        .where((entry) => entry.status == PrintJobStatus.failed)
        .length;
    return AppDialog(
      title: Row(
        children: [
          const Icon(Icons.print_outlined),
          const SizedBox(width: 10),
          const Expanded(child: Text('Fila de impressão')),
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
            : entries.isEmpty
            ? const AppEmptyState(
                icon: Icons.check_circle_outline,
                title: 'Nenhum cupom esperando',
                description:
                    'Tudo que foi enviado para impressão neste terminal já '
                    'saiu no papel.',
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    failed == 0
                        ? '${entries.length} cupom(ns) na fila. Eles saem '
                              'sozinhos assim que a impressora responder, com '
                              'até ${PrintQueueService.maximumAttempts} '
                              'tentativas cada.'
                        : '$failed de ${entries.length} pararam de tentar '
                              'sozinhos e esperam a sua decisão.',
                    style: TextStyle(color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView.separated(
                      itemCount: entries.length,
                      separatorBuilder: (_, _) => const Divider(height: 1),
                      itemBuilder: (_, index) => _tile(entries[index], scheme),
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
        TextButton.icon(
          onPressed: loading || entries.isEmpty ? null : _clearAll,
          style: TextButton.styleFrom(foregroundColor: scheme.error),
          icon: const Icon(Icons.delete_sweep_outlined),
          label: const Text('Limpar fila'),
        ),
        FilledButton.icon(
          onPressed: loading || entries.isEmpty ? null : _retryAll,
          icon: const Icon(Icons.play_arrow_outlined),
          label: const Text('Tentar todos agora'),
        ),
      ],
    );
  }

  Widget _tile(PrintQueueEntry entry, ColorScheme scheme) {
    final isFailed = entry.status == PrintJobStatus.failed;
    final busy = busyEntryId == entry.id;
    final error = (entry.lastError ?? '').trim();
    final printer = PrinterDevice.fromJson(entry.printer);

    return ListTile(
      contentPadding: const EdgeInsets.symmetric(vertical: 8),
      leading: Icon(
        isFailed ? Icons.report_outlined : Icons.schedule_outlined,
        color: isFailed ? scheme.error : scheme.onSurfaceVariant,
      ),
      title: Text(
        _title(entry),
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            [
              printer.label,
              _statusLabel(entry),
              if (entry.attempts > 0)
                '${entry.attempts}/${PrintQueueService.maximumAttempts} '
                    'tentativa(s)',
              _createdAt(entry),
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
                  color: isFailed ? scheme.error : scheme.onSurfaceVariant,
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
                  tooltip: 'Ver o cupom',
                  onPressed: () => _showContent(entry),
                  icon: const Icon(Icons.receipt_long_outlined),
                ),
                IconButton(
                  tooltip: 'Tentar agora',
                  onPressed: () => _retry(entry),
                  icon: const Icon(Icons.refresh),
                ),
                IconButton(
                  tooltip: 'Descartar',
                  onPressed: () => _discard(entry),
                  icon: Icon(Icons.delete_outline, color: scheme.error),
                ),
              ],
            ),
    );
  }

  /// O cupom exatamente como ele iria para a impressora.
  ///
  /// É o que responde "saiu em branco" e "saiu cortado" sem depender de gastar
  /// papel para descobrir.
  void _showContent(PrintQueueEntry entry) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AppDialog(
        title: Row(
          children: [
            Expanded(child: Text(_title(entry))),
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
              entry.content,
              style: const TextStyle(fontFamily: 'Consolas', fontSize: 12),
            ),
          ),
        ),
        actions: [
          TextButton.icon(
            onPressed: () => copyError(dialogContext, entry.content),
            icon: const Icon(Icons.copy_all_outlined),
            label: const Text('Copiar'),
          ),
        ],
      ),
    );
  }

  static String _title(PrintQueueEntry entry) =>
      switch (PrintJobType.parse(entry.jobType)) {
        PrintJobType.receipt => 'Recibo de venda',
        PrintJobType.kitchen => 'Comanda de produção',
        PrintJobType.kitchenCancel => 'Cancelamento de item',
        PrintJobType.weighTicket => 'Nota de pesagem',
        PrintJobType.fiscalDanfe => 'DANFE NFC-e',
        PrintJobType.printerTest => 'Nota de teste',
        PrintJobType.other => entry.jobType,
      };

  static String _statusLabel(PrintQueueEntry entry) {
    if (entry.status == PrintJobStatus.failed) {
      return entry.attempts >= PrintQueueService.maximumAttempts
          ? 'Sem tentativas restantes'
          : 'Recusado';
    }
    if (entry.status == PrintJobStatus.printing) return 'Imprimindo';
    final next = entry.nextRetryAt;
    if (next == null) return 'Na fila';
    final wait = next.difference(DateTime.now().toUtc());
    if (wait.isNegative) return 'Na fila';
    return 'Nova tentativa em ${wait.inSeconds + 1}s';
  }

  static String _createdAt(PrintQueueEntry entry) {
    final created = entry.createdAt.toLocal();
    String two(int value) => value.toString().padLeft(2, '0');
    return '${two(created.day)}/${two(created.month)} '
        '${two(created.hour)}:${two(created.minute)}';
  }
}
