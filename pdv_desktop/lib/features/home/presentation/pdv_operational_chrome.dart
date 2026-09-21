import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';

import '../../../core/network/api_client.dart';
import '../../devices/printing/printer.dart';
import 'pdv_status_indicators.dart';

class PdvOperationalBar extends StatelessWidget {
  const PdvOperationalBar({
    super.key,
    required this.cashName,
    required this.operatorName,
    required this.shiftLabel,
    required this.cashOpen,
    required this.network,
    required this.printer,
    required this.syncPending,
    this.trailing,
  });

  final String cashName;
  final String operatorName;
  final String shiftLabel;
  final bool cashOpen;
  final NetworkStatus network;
  final ValueListenable<PrinterAvailability> printer;
  final bool syncPending;

  /// Encaixe no fim da barra, para o que é estado e não cadastro — hoje o sino
  /// de notificações. Opcional porque a barra é reutilizável e os testes dela
  /// a montam sozinha, sem o `ErrorCenterScope` que o sino exige.
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: [
          Expanded(
            child: _Identity(
              cashName: cashName,
              operatorName: operatorName,
              shiftLabel: shiftLabel,
              cashOpen: cashOpen,
            ),
          ),
          PdvStatusIndicator(
            icon: network.hasConnection
                ? Icons.lan_outlined
                : Icons.link_off_outlined,
            label: network.hasConnection ? 'Servidor local' : 'Sem servidor',
            tone: network.hasConnection
                ? const Color(0xFF166534)
                : scheme.error,
          ),
          const SizedBox(width: 14),
          PdvStatusIndicator(
            icon: syncPending
                ? Icons.cloud_upload_outlined
                : Icons.cloud_outlined,
            label: syncPending
                ? 'Sincronização pendente'
                : 'Nuvem não monitorada',
            tone: syncPending
                ? const Color(0xFF9A5B00)
                : scheme.onSurfaceVariant,
          ),
          const SizedBox(width: 14),
          ValueListenableBuilder<PrinterAvailability>(
            valueListenable: printer,
            builder: (_, status, _) => PdvPrinterStatus(status: status),
          ),
          if (trailing != null) ...[const SizedBox(width: 8), trailing!],
        ],
      ),
    );
  }
}

class _Identity extends StatelessWidget {
  const _Identity({
    required this.cashName,
    required this.operatorName,
    required this.shiftLabel,
    required this.cashOpen,
  });

  final String cashName;
  final String operatorName;
  final String shiftLabel;
  final bool cashOpen;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Flexible(
        flex: 3,
        child: Row(
          children: [
            Flexible(
              child: Text(
                cashName,
                overflow: TextOverflow.ellipsis,
                maxLines: 1,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
            const SizedBox(width: 8),
            Text(
              cashOpen ? 'Aberto' : 'Fechado',
              style: TextStyle(
                color: cashOpen
                    ? const Color(0xFF166534)
                    : Theme.of(context).colorScheme.error,
                fontSize: 12,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
      const SizedBox(width: 12),
      Expanded(
        flex: 2,
        child: Text(
          'Operador: $operatorName',
          overflow: TextOverflow.ellipsis,
          maxLines: 1,
          style: const TextStyle(fontSize: 13),
        ),
      ),
      const SizedBox(width: 12),
      Expanded(
        flex: 3,
        child: Text(
          shiftLabel,
          overflow: TextOverflow.ellipsis,
          maxLines: 1,
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            fontSize: 12,
          ),
        ),
      ),
    ],
  );
}
