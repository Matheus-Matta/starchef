import 'package:flutter/material.dart';

import '../../../core/widgets/shadcn_layout.dart';
import '../services/mobile_print_agent.dart';

class PrintQueuePage extends StatefulWidget {
  const PrintQueuePage({super.key, required this.agent});

  final MobilePrintAgent agent;

  @override
  State<PrintQueuePage> createState() => _PrintQueuePageState();
}

class _PrintQueuePageState extends State<PrintQueuePage> {
  List<Map<String, dynamic>> _jobs = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final jobs = await widget.agent.loadQueue();
      if (mounted) setState(() => _jobs = jobs);
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => AppPageScaffold(
    title: 'Fila de impressão',
    actions: [
      IconButton(
        tooltip: 'Atualizar fila',
        onPressed: _loading ? null : _refresh,
        icon: const Icon(Icons.refresh),
      ),
    ],
    body: _body(context),
  );

  Widget _body(BuildContext context) {
    if (_loading && _jobs.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && _jobs.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_outlined, size: 40),
              const SizedBox(height: 12),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: _refresh,
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ),
      );
    }
    if (_jobs.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'A fila ativa está vazia. Trabalhos que falharem cinco vezes '
            'saem daqui e ficam registrados como falha no backend.',
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _jobs.length,
        itemBuilder: (context, index) => _QueueJobCard(job: _jobs[index]),
      ),
    );
  }
}

class _QueueJobCard extends StatelessWidget {
  const _QueueJobCard({required this.job});

  final Map<String, dynamic> job;

  @override
  Widget build(BuildContext context) {
    final status = '${job['status'] ?? 'desconhecido'}';
    final payload = job['payload'] is Map
        ? Map<String, dynamic>.from(job['payload'] as Map)
        : const <String, dynamic>{};
    final text = '${payload['text_content'] ?? ''}'.trim();
    final error = '${job['error_message'] ?? ''}'.trim();
    final createdAt = '${job['created_at'] ?? ''}';
    return Card(
      child: ListTile(
        leading: Icon(_statusIcon(status)),
        title: Text(_jobTitle('${job['job_type'] ?? ''}')),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Status: ${_statusLabel(status)}'),
            if (createdAt.isNotEmpty) Text('Criado: $createdAt'),
            if (text.isNotEmpty)
              Text(text, maxLines: 4, overflow: TextOverflow.ellipsis),
            if (error.isNotEmpty)
              Text(
                'Erro: $error',
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
          ],
        ),
        isThreeLine: true,
      ),
    );
  }

  IconData _statusIcon(String status) => switch (status) {
    'failed' => Icons.error_outline,
    'claimed' => Icons.hourglass_top,
    _ => Icons.receipt_long_outlined,
  };

  String _statusLabel(String status) => switch (status) {
    'pending' => 'Aguardando impressão',
    'rendered' => 'Pronto para imprimir',
    'claimed' => 'Em processamento',
    'failed' => 'Falhou',
    _ => status,
  };

  String _jobTitle(String type) => switch (type) {
    'kitchen' || 'kitchen_ticket' => 'Comanda da cozinha',
    'bar_ticket' => 'Comanda do bar',
    'kitchen_cancel' || 'kitchen_cancellation' => 'Cancelamento de item',
    _ => type.isEmpty ? 'Trabalho de impressão' : type,
  };
}
