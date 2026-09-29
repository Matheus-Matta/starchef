import 'package:flutter/material.dart';

import '../widgets/app_toast.dart';
import 'mobile_update_service.dart';
import 'update_download_sheet.dart';

/// Consulta sob demanda e, quando houver APK novo, já abre o fluxo de
/// download e instalação. O Android ainda pede a confirmação final.
Future<void> checkMobileUpdateNow(
  BuildContext context, {
  MobileUpdateService? service,
}) async {
  final ownsService = service == null;
  final updates = service ?? MobileUpdateService();
  final messenger = ScaffoldMessenger.of(context);
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(const SnackBar(content: Text('Buscando atualizações...')));
  try {
    final status = await updates.check();
    if (!context.mounted) return;
    messenger.hideCurrentSnackBar();
    switch (status.phase) {
      case UpdatePhase.available:
        await showUpdateDownloadSheet(context, updates, status.apk!);
      case UpdatePhase.upToDate:
        final version = status.installed.isEmpty
            ? ''
            : ' (${status.installed})';
        showToast(context, 'O StarChef já está atualizado$version.');
      case UpdatePhase.unavailable:
        showToast(
          context,
          status.reason.isEmpty
              ? 'Não foi possível buscar atualizações.'
              : status.reason,
        );
      case UpdatePhase.checking:
        showToast(context, 'A busca de atualização já está em andamento.');
    }
  } finally {
    if (ownsService) updates.dispose();
  }
}
