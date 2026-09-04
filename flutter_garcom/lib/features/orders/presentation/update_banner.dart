import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/update/garcom_update_controller.dart';

/// Aviso de nova versão do app, no mesmo lugar/estilo do [SyncBanner] — um
/// estado visível ao entrar no app, não um diálogo que interrompe o
/// atendimento.
class UpdateBanner extends StatelessWidget {
  const UpdateBanner({super.key, required this.controller});

  final GarcomUpdateController controller;

  @override
  Widget build(BuildContext context) {
    if (controller.phase == GarcomUpdateBannerPhase.hidden) {
      return const SizedBox.shrink();
    }
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: scheme.primaryContainer,
          borderRadius: AppTheme.radius,
          border: Border.all(color: scheme.primary.withValues(alpha: .35)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(
                  controller.phase == GarcomUpdateBannerPhase.failed
                      ? Icons.error_outline
                      : Icons.system_update_alt,
                  size: 18,
                  color: scheme.onPrimaryContainer,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _message(controller),
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                      color: scheme.onPrimaryContainer,
                    ),
                  ),
                ),
                if (controller.phase == GarcomUpdateBannerPhase.available ||
                    controller.phase == GarcomUpdateBannerPhase.failed)
                  TextButton(
                    onPressed: controller.downloadAndInstall,
                    style: TextButton.styleFrom(
                      minimumSize: Size.zero,
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                    ),
                    child: const Text('Baixar', style: TextStyle(fontSize: 12.5)),
                  ),
                if (controller.phase ==
                        GarcomUpdateBannerPhase.downloading ||
                    controller.phase == GarcomUpdateBannerPhase.readyToInstall)
                  const SizedBox.square(
                    dimension: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            if (controller.phase == GarcomUpdateBannerPhase.downloading) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(value: controller.progress),
            ],
          ],
        ),
      ),
    );
  }

  String _message(GarcomUpdateController controller) => switch (controller
      .phase) {
    GarcomUpdateBannerPhase.available =>
      'Nova versão do app disponível.',
    GarcomUpdateBannerPhase.downloading => 'Baixando atualização...',
    GarcomUpdateBannerPhase.readyToInstall =>
      'Abrindo o instalador...',
    GarcomUpdateBannerPhase.failed =>
      controller.detail ?? 'Não foi possível atualizar.',
    GarcomUpdateBannerPhase.hidden => '',
  };
}
