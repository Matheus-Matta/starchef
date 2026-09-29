import 'package:flutter/material.dart';

import '../update/pdv_update_service.dart';
import 'pdv_version_indicator.dart';

class PdvUpdateActions extends StatelessWidget {
  const PdvUpdateActions({
    super.key,
    required this.status,
    required this.onCheckForUpdates,
  });

  final PdvUpdateStatus? status;
  final Future<void> Function()? onCheckForUpdates;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      PdvVersionIndicator(
        status: status,
        onPressed: onCheckForUpdates == null
            ? null
            : () => onCheckForUpdates!(),
      ),
      if (onCheckForUpdates != null) ...[
        const SizedBox(height: 8),
        TextButton.icon(
          key: const Key('check-updates-login'),
          onPressed: () => onCheckForUpdates!(),
          icon: const Icon(Icons.system_update_alt, size: 18),
          label: const Text('Buscar atualizações'),
        ),
      ],
    ],
  );
}
