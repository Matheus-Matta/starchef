import 'package:flutter/material.dart';

import '../../../core/widgets/shadcn_layout.dart';
import '../services/mobile_print_agent.dart';

class PrintStatusPage extends StatelessWidget {
  const PrintStatusPage({super.key, required this.agent});

  final MobilePrintAgent agent;

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: agent,
    builder: (context, _) => AppPageScaffold(
      title: 'Impressão pelo celular',
      actions: [
        IconButton(
          tooltip: 'Sincronizar agora',
          onPressed: agent.state == PrintAgentState.syncing
              ? null
              : agent.runNow,
          icon: const Icon(Icons.refresh),
        ),
      ],
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _StatusCard(agent: agent),
          const SizedBox(height: 16),
          Text(
            'Impressoras do backend',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'O telefone imprime somente novas comandas e cancelamentos, '
            'conforme o roteamento definido pelo backend.',
          ),
          const SizedBox(height: 8),
          if (agent.printers.isEmpty)
            const ListTile(
              leading: Icon(Icons.print_disabled_outlined),
              title: Text('Nenhuma impressora disponível'),
              subtitle: Text('Confira o cadastro e a permissão do usuário.'),
            ),
          for (final printer in agent.printers)
            ListTile(
              leading: Icon(
                printer.supportsMobile ? Icons.print_outlined : Icons.block,
              ),
              title: Text(printer.name),
              subtitle: Text(
                printer.acceptsAutomaticJobs
                    ? '${printer.host}:${printer.port} • '
                          '${printer.isEscPos ? 'ESC/POS' : 'texto'}'
                    : printer.supportsMobile
                    ? 'Impressão automática desativada no backend'
                    : 'Somente impressoras TCP/IP podem ser usadas no celular',
              ),
            ),
        ],
      ),
    ),
  );
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({required this.agent});

  final MobilePrintAgent agent;

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(_title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Text('${agent.supportedPrinters} impressora(s) utilizável(is)'),
          Text('${agent.printedCount} trabalho(s) impresso(s) nesta sessão'),
          if (agent.lastError != null) ...[
            const SizedBox(height: 8),
            Text(
              agent.lastError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          if (!agent.permissionGranted) ...[
            const SizedBox(height: 12),
            const Text(
              'A permissão de dispositivos próximos foi negada. A lista do '
              'backend continua visível, mas o acesso à rede local pode falhar.',
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton(
                  onPressed: agent.requestPermissionAgain,
                  child: const Text('Pedir novamente'),
                ),
                TextButton(
                  onPressed: agent.openSystemSettings,
                  child: const Text('Abrir configurações'),
                ),
              ],
            ),
          ],
        ],
      ),
    ),
  );

  String get _title => switch (agent.state) {
    PrintAgentState.stopped => 'Agente parado',
    PrintAgentState.requestingPermission => 'Solicitando permissão',
    PrintAgentState.syncing => 'Buscando trabalhos',
    PrintAgentState.ready => 'Impressão ativa',
    PrintAgentState.error => 'Impressão com falha',
  };
}
