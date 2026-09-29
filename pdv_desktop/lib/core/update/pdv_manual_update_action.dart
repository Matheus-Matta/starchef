import 'package:flutter/material.dart';

import 'pdv_auto_updater.dart';

Future<void> checkAndInstallPdvUpdate({
  required BuildContext? context,
  required PdvAutoUpdater updater,
  required Future<void> Function() closePdv,
}) async {
  final messenger = context == null ? null : ScaffoldMessenger.maybeOf(context);
  await updater.checkAndInstall(closePdv: closePdv);
  if (updater.phase == PdvAutoUpdatePhase.restarting ||
      messenger == null ||
      !messenger.mounted) {
    return;
  }
  final message = switch (updater.phase) {
    PdvAutoUpdatePhase.upToDate => 'O StarChef já está atualizado.',
    PdvAutoUpdatePhase.failed =>
      updater.detail ?? 'Não foi possível buscar atualizações.',
    _ => 'A busca de atualização já está em andamento.',
  };
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));
}
