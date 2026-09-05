import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/update/garcom_update_controller.dart';
import '../../../core/widgets/shadcn_layout.dart';

/// Aviso de nova versão do app, no mesmo lugar e no mesmo formato do
/// [SyncBanner] — um estado visível ao entrar no app, não um diálogo que
/// interrompe o atendimento.
class UpdateBanner extends StatelessWidget {
  const UpdateBanner({super.key, required this.controller});

  final GarcomUpdateController controller;

  @override
  Widget build(BuildContext context) {
    final phase = controller.phase;
    if (phase == GarcomUpdateBannerPhase.hidden) {
      return const SizedBox.shrink();
    }
    final failed = phase == GarcomUpdateBannerPhase.failed;
    final working =
        phase == GarcomUpdateBannerPhase.downloading ||
        phase == GarcomUpdateBannerPhase.readyToInstall;
    return Padding(
      padding: AppTheme.bannerPadding,
      child: AppNotice(
        tone: failed ? AppNoticeTone.danger : AppNoticeTone.info,
        icon: failed ? Icons.error_outline : Icons.system_update_alt,
        message: _message(phase),
        actionLabel: phase == GarcomUpdateBannerPhase.available || failed
            ? 'Baixar'
            : null,
        onAction: controller.downloadAndInstall,
        trailing: working
            ? const SizedBox.square(
                dimension: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : null,
        footer: phase == GarcomUpdateBannerPhase.downloading
            ? LinearProgressIndicator(value: controller.progress)
            : null,
      ),
    );
  }

  String _message(GarcomUpdateBannerPhase phase) => switch (phase) {
    GarcomUpdateBannerPhase.available => 'Nova versão do app disponível.',
    GarcomUpdateBannerPhase.downloading => 'Baixando atualização...',
    GarcomUpdateBannerPhase.readyToInstall => 'Abrindo o instalador...',
    GarcomUpdateBannerPhase.failed =>
      controller.detail ?? 'Não foi possível atualizar.',
    GarcomUpdateBannerPhase.hidden => '',
  };
}
