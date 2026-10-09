import 'package:flutter/material.dart';

import '../../../core/config/api_settings.dart';
import '../../../core/widgets/app_toast.dart';

/// Liga ou desliga "Perguntar mesa" neste aparelho e avisa o que mudou.
Future<void> alternarPerguntarMesa(
  BuildContext context,
  ApiSettings settings,
) async {
  final ligar = !settings.askTable;
  await settings.setAskTable(ligar);
  if (!context.mounted) return;
  showToast(
    context,
    ligar
        ? 'O app vai perguntar a mesa.'
        : 'O app não vai mais perguntar a mesa.',
  );
}
