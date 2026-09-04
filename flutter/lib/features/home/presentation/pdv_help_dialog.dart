import 'package:flutter/material.dart';

import '../../../core/input/pdv_input_router.dart';
import '../../../core/input/pdv_screen.dart';
import '../../../core/input/pdv_shortcuts.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_dialog.dart';

/// O estado do leitor serial, como a ajuda o apresenta.
class ScannerStatus {
  const ScannerStatus({
    required this.connected,
    this.portLabel = '',
    this.detail = '',
  });

  final bool connected;
  final String portLabel;
  final String detail;
}

/// Ajuda do PDV: atalhos, leitura de código e um lugar para testar.
///
/// A lista de atalhos NÃO é escrita aqui — ela é lida do mesmo
/// [PdvShortcuts] que o roteador consulta para decidir o que cada tecla faz.
/// Enquanto documentação e comportamento viviam separados, trocar uma tecla
/// exigia lembrar de editar a tela de ajuda, e ninguém lembra: o operador
/// acabava com uma lista que descreve um PDV que não existe mais.
class PdvHelpDialog extends StatefulWidget {
  const PdvHelpDialog({
    super.key,
    required this.screen,
    required this.hasOrder,
    required this.scannerStatus,
    required this.lastCode,
    this.onTestCode,
  });

  final PdvScreen screen;
  final bool hasOrder;
  final ScannerStatus scannerStatus;

  /// Última leitura que o roteador entregou — o diagnóstico mais direto de
  /// "o leitor está mesmo chegando aqui?".
  final ScannedCode? lastCode;

  /// Interpreta um código SEM executar a ação, para o operador conferir o que
  /// aconteceria antes de bipar de verdade na frente do cliente.
  final Future<String> Function(String code)? onTestCode;

  static Future<void> show(
    BuildContext context, {
    required PdvScreen screen,
    required bool hasOrder,
    required ScannerStatus scannerStatus,
    ScannedCode? lastCode,
    Future<String> Function(String code)? onTestCode,
  }) => showDialog<void>(
    context: context,
    builder: (_) => PdvHelpDialog(
      screen: screen,
      hasOrder: hasOrder,
      scannerStatus: scannerStatus,
      lastCode: lastCode,
      onTestCode: onTestCode,
    ),
  );

  @override
  State<PdvHelpDialog> createState() => _PdvHelpDialogState();
}

class _PdvHelpDialogState extends State<PdvHelpDialog> {
  final TextEditingController _search = TextEditingController();
  final TextEditingController _testCode = TextEditingController();
  String _testResult = '';
  bool _testing = false;

  @override
  void dispose() {
    _search.dispose();
    _testCode.dispose();
    super.dispose();
  }

  List<PdvShortcut> get _visible {
    final term = _search.text.trim().toLowerCase();
    final shortcuts = PdvShortcuts.forScreen(widget.screen);
    if (term.isEmpty) return shortcuts;
    return shortcuts
        .where(
          (shortcut) =>
              shortcut.label.toLowerCase().contains(term) ||
              shortcut.description.toLowerCase().contains(term) ||
              shortcut.keysLabel.toLowerCase().contains(term),
        )
        .toList();
  }

  Future<void> _runTest() async {
    final handler = widget.onTestCode;
    final code = PdvInputRouter.normalize(_testCode.text);
    if (handler == null) return;
    if (code.isEmpty) {
      setState(() {
        _testResult =
            'Isto não seria lido como código: um código não tem espaços, '
            'não tem mais de uma linha e cabe em 64 caracteres.';
      });
      return;
    }
    setState(() => _testing = true);
    final result = await handler(code);
    if (!mounted) return;
    setState(() {
      _testing = false;
      _testResult = result;
    });
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final shortcuts = _visible;
    final groups = PdvShortcuts.groups
        .map(
          (group) => MapEntry(
            group,
            shortcuts.where((item) => item.group == group).toList(),
          ),
        )
        .where((entry) => entry.value.isNotEmpty)
        .toList();

    return AppDialog(
      scrollable: true,
      maxWidth: 860,
      title: Row(
        children: [
          const Icon(Icons.help_outline),
          const SizedBox(width: 10),
          Expanded(child: Text('Ajuda · ${widget.screen.label}')),
        ],
      ),
      content: SizedBox(
        width: 820,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _ScannerCard(
              screen: widget.screen,
              status: widget.scannerStatus,
              lastCode: widget.lastCode,
            ),
            const SizedBox(height: 14),
            if (widget.onTestCode != null) ...[
              _sectionTitle(context, 'Testar um código'),
              const SizedBox(height: 6),
              Text(
                'Bipe ou cole aqui: o PDV diz o que faria, sem fazer. '
                'É o lugar de descobrir que uma etiqueta está errada antes de '
                'descobrir com o cliente esperando.',
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 12.5,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _testCode,
                      decoration: const InputDecoration(
                        isDense: true,
                        border: OutlineInputBorder(),
                        hintText: 'Ex.: 7891000100103',
                      ),
                      onSubmitted: (_) => _runTest(),
                    ),
                  ),
                  const SizedBox(width: 10),
                  FilledButton.icon(
                    onPressed: _testing ? null : _runTest,
                    icon: const Icon(Icons.play_arrow_outlined, size: 18),
                    label: const Text('Interpretar'),
                  ),
                ],
              ),
              if (_testResult.isNotEmpty) ...[
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: scheme.surfaceContainer,
                    borderRadius: AppTheme.radius,
                    border: Border.all(color: scheme.outlineVariant),
                  ),
                  child: Text(_testResult),
                ),
              ],
              const SizedBox(height: 18),
            ],
            _sectionTitle(context, 'Atalhos'),
            const SizedBox(height: 8),
            TextField(
              controller: _search,
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                isDense: true,
                prefixIcon: Icon(Icons.search, size: 18),
                border: OutlineInputBorder(),
                hintText: 'Buscar por nome ou tecla',
              ),
            ),
            const SizedBox(height: 12),
            if (groups.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 18),
                child: Text(
                  'Nenhum atalho com esse nome nesta tela.',
                  style: TextStyle(color: scheme.onSurfaceVariant),
                ),
              ),
            for (final entry in groups) ...[
              Padding(
                padding: const EdgeInsets.only(top: 6, bottom: 6),
                child: Text(
                  entry.key,
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 12,
                    letterSpacing: .6,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ),
              for (final shortcut in entry.value)
                _ShortcutRow(
                  shortcut: shortcut,
                  enabled: !shortcut.requiresOrder || widget.hasOrder,
                ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Fechar'),
        ),
      ],
    );
  }

  Widget _sectionTitle(BuildContext context, String text) => Text(
    text,
    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
  );
}

class _ScannerCard extends StatelessWidget {
  const _ScannerCard({
    required this.screen,
    required this.status,
    required this.lastCode,
  });

  final PdvScreen screen;
  final ScannerStatus status;
  final ScannedCode? lastCode;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: AppTheme.radius,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.qr_code_scanner_outlined, size: 18),
              const SizedBox(width: 8),
              const Text(
                'Leitura de código',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
              const Spacer(),
              _StatusChip(
                label: status.connected
                    ? 'Serial: ${status.portLabel.isEmpty ? 'conectado' : status.portLabel}'
                    : 'Serial: não conectado',
                positive: status.connected,
              ),
            ],
          ),
          const SizedBox(height: 10),
          _line(scheme, 'Nesta tela', screen.codeBehaviour),
          _line(
            scheme,
            'Leitor USB',
            'Funciona como teclado: digita o código rápido e termina com Enter '
                'ou Tab. Esse Enter é consumido pela leitura — ele nunca '
                'confirma um pagamento nem fecha um modal por conta própria. '
                'Com o cursor dentro de um campo, o leitor escreve no campo, '
                'como qualquer digitação.',
          ),
          _line(
            scheme,
            'Área de transferência',
            'F8 ou Ctrl + Shift + V interpretam o texto copiado como uma '
                'leitura. Ctrl + V continua colando normalmente. Nada é lido '
                'em segundo plano: senhas e textos copiados não viram código.',
          ),
          if (status.detail.isNotEmpty)
            _line(scheme, 'Leitor serial', status.detail),
          _line(
            scheme,
            'Última leitura',
            lastCode == null
                ? 'Nenhuma leitura ainda nesta sessão.'
                : '${lastCode!.value}  ·  ${lastCode!.sourceLabel}',
          ),
        ],
      ),
    );
  }

  Widget _line(ColorScheme scheme, String label, String value) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 150,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
              color: scheme.onSurfaceVariant,
            ),
          ),
        ),
        Expanded(child: Text(value, style: const TextStyle(fontSize: 12.5))),
      ],
    ),
  );
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.positive});

  final String label;
  final bool positive;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = positive ? scheme.primary : scheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11.5,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

class _ShortcutRow extends StatelessWidget {
  const _ShortcutRow({required this.shortcut, required this.enabled});

  final PdvShortcut shortcut;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Opacity(
      opacity: enabled ? 1 : .55,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 128,
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: scheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: scheme.outlineVariant),
              ),
              child: Text(
                shortcut.keysLabel,
                style: const TextStyle(
                  fontFamily: 'monospace',
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          shortcut.label,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                      ),
                      if (!enabled) ...[
                        const SizedBox(width: 8),
                        Text(
                          '· sem pedido aberto',
                          style: TextStyle(
                            fontSize: 11.5,
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                  Text(
                    shortcut.description,
                    style: TextStyle(
                      fontSize: 12.5,
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
