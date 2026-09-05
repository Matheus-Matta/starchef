import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/relay/principal_client.dart';
import '../../../core/relay/principal_diagnostics.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/app_toast.dart';

/// Mostra onde a ligação com o Caixa Principal parou.
///
/// O texto é copiável de propósito: quem está com o celular na mão quase nunca
/// é quem resolve, e mandar o resultado por mensagem evita a rodada de
/// "aparece um erro aqui" / "qual erro?".
Future<void> showPrincipalDiagnostics(
  BuildContext context, {
  required PrincipalClient client,
  required PrincipalConfig config,
  required RelayIdentity identity,
}) => showAppSheet<void>(
  context,
  builder: (context) => _DiagnosticsSheet(
    diagnostics: PrincipalDiagnostics(client: client),
    config: config,
    identity: identity,
  ),
);

class _DiagnosticsSheet extends StatefulWidget {
  const _DiagnosticsSheet({
    required this.diagnostics,
    required this.config,
    required this.identity,
  });

  final PrincipalDiagnostics diagnostics;
  final PrincipalConfig config;
  final RelayIdentity identity;

  @override
  State<_DiagnosticsSheet> createState() => _DiagnosticsSheetState();
}

class _DiagnosticsSheetState extends State<_DiagnosticsSheet> {
  List<ProbeStep> _steps = const [];
  bool _running = true;

  @override
  void initState() {
    super.initState();
    _run();
  }

  Future<void> _run() async {
    setState(() => _running = true);
    final steps = await widget.diagnostics.run(widget.config, widget.identity);
    if (!mounted) return;
    setState(() {
      _steps = steps;
      _running = false;
    });
  }

  String get _asText => [
    'StarChef Garçom — teste de conexão',
    'Caixa: ${widget.config.host}:${widget.config.port}',
    'Restaurante: ${widget.identity.restaurantId}',
    '',
    ..._steps.map((step) => '$step'),
  ].join('\n');

  Future<void> _copy() async {
    await Clipboard.setData(ClipboardData(text: _asText));
    if (mounted) showToast(context, 'Resultado copiado.');
  }

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppSheetHeader(
          title: 'Teste de conexão',
          subtitle: '${widget.config.host}:${widget.config.port}',
          trailing: _running
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : null,
        ),
        for (final step in _steps) _StepRow(step: step),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: ShadButton.outline(
                onPressed: _running ? null : _run,
                height: AppTheme.controlHeight,
                leading: const Icon(Icons.refresh, size: 18),
                child: const Text('Testar de novo'),
              ),
            ),
            const SizedBox(width: AppTheme.gap),
            Expanded(
              child: ShadButton(
                onPressed: _steps.isEmpty ? null : _copy,
                height: AppTheme.controlHeight,
                leading: const Icon(Icons.copy, size: 18),
                child: const Text('Copiar'),
              ),
            ),
          ],
        ),
      ],
    ),
  );
}

/// Uma etapa do teste: passou ou não, quanto demorou e o que aconteceu.
class _StepRow extends StatelessWidget {
  const _StepRow({required this.step});

  final ProbeStep step;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final elapsed = step.elapsed;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            step.ok ? Icons.check_circle : Icons.cancel,
            color: step.ok ? AppColors.success : scheme.error,
            size: 20,
          ),
          const SizedBox(width: AppTheme.gap),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  elapsed == null
                      ? step.name
                      : '${step.name} · ${elapsed.inMilliseconds} ms',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 2),
                SelectableText(
                  step.detail,
                  style: TextStyle(
                    fontSize: 13,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
