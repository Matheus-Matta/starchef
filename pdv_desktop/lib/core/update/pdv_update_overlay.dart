import 'package:flutter/material.dart';

import 'pdv_auto_updater.dart';

class PdvUpdateOverlay extends StatelessWidget {
  const PdvUpdateOverlay({
    super.key,
    required this.autoUpdater,
    required this.child,
  });

  final PdvAutoUpdater autoUpdater;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!autoUpdater.blocksInteraction) return child;
    final message = switch (autoUpdater.phase) {
      PdvAutoUpdatePhase.downloading => 'Baixando atualização segura…',
      PdvAutoUpdatePhase.preparing => 'Preparando atualização…',
      PdvAutoUpdatePhase.restarting => 'Reiniciando o StarChef…',
      _ => 'Atualizando o StarChef…',
    };
    return Stack(
      fit: StackFit.expand,
      children: [
        child,
        ColoredBox(
          color: Theme.of(context).scaffoldBackgroundColor,
          child: Center(
            child: SizedBox(
              width: 420,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.system_update_alt, size: 54),
                  const SizedBox(height: 20),
                  Text(message, style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 16),
                  LinearProgressIndicator(value: autoUpdater.progress),
                  const SizedBox(height: 12),
                  const Text(
                    'Não desligue o computador. Se a nova versão não abrir, '
                    'a versão anterior será restaurada automaticamente.',
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
