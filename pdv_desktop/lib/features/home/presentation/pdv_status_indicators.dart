import 'package:flutter/material.dart';

import '../../devices/printing/printer.dart';

class PdvPrinterStatus extends StatelessWidget {
  const PdvPrinterStatus({super.key, required this.status});

  final PrinterAvailability status;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final available = status.phase == PrinterAvailabilityPhase.available;
    final checking = status.phase == PrinterAvailabilityPhase.checking;
    final notConfigured =
        status.phase == PrinterAvailabilityPhase.notConfigured;
    return PdvStatusIndicator(
      icon: available
          ? Icons.print_outlined
          : checking
          ? Icons.sync
          : Icons.print_disabled_outlined,
      label: available
          ? 'Impressora pronta'
          : checking
          ? 'Verificando impressora'
          : notConfigured
          ? 'Impressora não configurada'
          : 'Tentando impressora',
      tone: available
          ? scheme.onSurfaceVariant
          : checking
          ? scheme.onSurfaceVariant
          : const Color(0xFF9A5B00),
    );
  }
}

class PdvStatusIndicator extends StatelessWidget {
  const PdvStatusIndicator({
    super.key,
    required this.icon,
    required this.label,
    required this.tone,
  });

  final IconData icon;
  final String label;
  final Color tone;

  @override
  Widget build(BuildContext context) => Tooltip(
    message: label,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 17, color: tone),
        const SizedBox(width: 5),
        Text(
          label,
          style: TextStyle(
            color: tone,
            fontSize: 12,
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    ),
  );
}
