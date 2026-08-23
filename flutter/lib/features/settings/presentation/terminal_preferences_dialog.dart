import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

import '../../../core/hardware/scale/scale_protocol.dart';
import '../../../core/hardware/scale/scale_transport.dart';
import '../../../core/storage/local_preferences.dart';

/// Preferências que pertencem a este terminal, não à conta.
///
/// Timeout da comanda, tolerância de estabilidade, alertas sonoros e impressão
/// automática são decisões de cada balcão — dois terminais do mesmo
/// restaurante podem precisar de valores diferentes. Por isso ficam no
/// `preferences.json` local e não no cadastro do backend.
class TerminalPreferencesDialog extends StatefulWidget {
  const TerminalPreferencesDialog({
    super.key,
    required this.preferences,
    this.detectedPorts,
  });

  final LocalPreferences preferences;
  final List<String>? detectedPorts;

  static Future<void> show(
    BuildContext context,
    LocalPreferences preferences,
  ) => showDialog<void>(
    context: context,
    builder: (_) => TerminalPreferencesDialog(preferences: preferences),
  );

  @override
  State<TerminalPreferencesDialog> createState() =>
      _TerminalPreferencesDialogState();
}

class _TerminalPreferencesDialogState extends State<TerminalPreferencesDialog> {
  late int commandTimeoutSeconds = widget.preferences.commandTimeout.inSeconds;
  late double toleranceGrams = widget.preferences.stabilityToleranceKg * 1000;
  late bool audibleAlerts = widget.preferences.audibleAlerts;
  late bool autoPrint = widget.preferences.autoPrint;

  Future<void> _save() async {
    final preferences = widget.preferences;
    await preferences.setCommandTimeout(
      Duration(seconds: commandTimeoutSeconds),
    );
    await preferences.setStabilityToleranceKg(toleranceGrams / 1000);
    await preferences.setAudibleAlerts(audibleAlerts);
    await preferences.setAutoPrint(autoPrint);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AppDialog(
      scrollable: true,
      maxWidth: 668,
      title: Row(
        children: [
          const Icon(Icons.tune),
          const SizedBox(width: 10),
          const Expanded(child: Text('Preferências deste terminal')),
          IconButton(
            tooltip: 'Fechar',
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close),
          ),
        ],
      ),
      content: SizedBox(
        width: 620,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            _section('Balança Rápida', scheme),
            _slider(
              label: 'Tempo para ler a comanda',
              value: commandTimeoutSeconds.toDouble(),
              min: 10,
              max: 300,
              divisions: 29,
              display: '$commandTimeoutSeconds s',
              helper:
                  'Depois desse tempo a estação avisa e, se ninguém ler a '
                  'comanda, cancela a pesagem e volta a esperar peso.',
              onChanged: (value) =>
                  setState(() => commandTimeoutSeconds = value.round()),
            ),
            _slider(
              label: 'Tolerância de estabilidade',
              value: toleranceGrams,
              min: 1,
              max: 50,
              divisions: 49,
              display: '${toleranceGrams.round()} g',
              helper:
                  'Oscilação ignorada entre leituras. Aumente se a bancada '
                  'vibra e o peso nunca estabiliza.',
              onChanged: (value) => setState(() => toleranceGrams = value),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: audibleAlerts,
              onChanged: (value) => setState(() => audibleAlerts = value),
              title: const Text('Alertas sonoros'),
              subtitle: const Text(
                'Bipe ao confirmar o peso, ao aceitar a comanda e no aviso '
                'de tempo esgotado.',
              ),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: autoPrint,
              onChanged: (value) => setState(() => autoPrint = value),
              title: const Text('Imprimir o cupom automaticamente'),
              subtitle: const Text(
                'Desligue apenas se o cupom for emitido por outro caminho; '
                'o pedido continua sendo lançado normalmente.',
              ),
            ),
            const SizedBox(height: 18),
            _section('Diagnóstico do terminal', scheme),
            _readOnlyRow(
              icon: Icons.usb,
              label: 'Portas seriais detectadas',
              value: _portsSummary(),
              scheme: scheme,
            ),
            _readOnlyRow(
              icon: Icons.settings_input_component,
              label: 'Protocolos de balança suportados',
              value: ScaleProtocol.available
                  .map((protocol) => protocol.label)
                  .join(', '),
              scheme: scheme,
            ),
            const SizedBox(height: 8),
            Text(
              'O protocolo, a porta e o baud rate de cada balança ficam no '
              'cadastro do equipamento, porque valem para todos os terminais '
              'que a usam.',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          onPressed: _save,
          icon: const Icon(Icons.check),
          label: const Text('Salvar'),
        ),
      ],
    );
  }

  Widget _section(String title, ColorScheme scheme) => Padding(
    padding: const EdgeInsets.only(bottom: 8),
    child: Text(
      title.toUpperCase(),
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w900,
        letterSpacing: .8,
        color: scheme.primary,
      ),
    ),
  );

  Widget _slider({
    required String label,
    required double value,
    required double min,
    required double max,
    required int divisions,
    required String display,
    required String helper,
    required ValueChanged<double> onChanged,
  }) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
              ),
              Text(
                display,
                style: TextStyle(
                  fontWeight: FontWeight.w900,
                  color: scheme.primary,
                ),
              ),
            ],
          ),
          Slider(
            value: value.clamp(min, max),
            min: min,
            max: max,
            divisions: divisions,
            onChanged: onChanged,
          ),
          Text(
            helper,
            style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
          ),
        ],
      ),
    );
  }

  Widget _readOnlyRow({
    required IconData icon,
    required String label,
    required String value,
    required ColorScheme scheme,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 19, color: scheme.onSurfaceVariant),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w800,
                ),
              ),
              Text(
                value,
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ],
    ),
  );

  String _portsSummary() {
    final ports = widget.detectedPorts ?? SerialScaleTransport.availablePorts();
    return ports.isEmpty ? 'Nenhuma porta encontrada' : ports.join(', ');
  }
}
