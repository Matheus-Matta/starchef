import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

import '../../../core/storage/local_preferences.dart';

/// Permite digitar manualmente a URL da API a partir da tela de login —
/// escape hatch para quando o terminal foi instalado sem `--dart-define`/
/// `.env` (ou precisa apontar para outro ambiente pontualmente). Fica salvo
/// em `LocalPreferences` e tem prioridade sobre a configuração de build (ver
/// `AppConfig.load`), então vale mesmo quando o instalador já veio com uma
/// URL embutida.
///
/// A mudança só é lida no próximo boot (`AppConfig.load` roda uma vez antes
/// de `runApp`), então salvar aqui não reconecta a sessão atual — só avisa
/// que é preciso reabrir o app.
class ApiUrlSettingsDialog extends StatefulWidget {
  const ApiUrlSettingsDialog({super.key, required this.preferences});

  final LocalPreferences preferences;

  static Future<void> show(
    BuildContext context,
    LocalPreferences preferences,
  ) => showDialog<void>(
    context: context,
    builder: (_) => ApiUrlSettingsDialog(preferences: preferences),
  );

  @override
  State<ApiUrlSettingsDialog> createState() => _ApiUrlSettingsDialogState();
}

class _ApiUrlSettingsDialogState extends State<ApiUrlSettingsDialog> {
  late final _urlController = TextEditingController(
    text: widget.preferences.apiBaseUrlOverride ?? '',
  );
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  String? _validateUrl(String? value) {
    final text = value?.trim() ?? '';
    if (text.isEmpty) return null; // vazio = remove o override, é válido.
    final uri = Uri.tryParse(text);
    final valid =
        uri != null &&
        (uri.scheme == 'http' || uri.scheme == 'https') &&
        uri.host.isNotEmpty;
    return valid
        ? null
        : 'Informe uma URL completa (ex.: https://api.seu-dominio.com/api/v1).';
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final text = _urlController.text.trim();
    await widget.preferences.setApiBaseUrlOverride(text.isEmpty ? null : text);
    if (!mounted) return;
    Navigator.pop(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          text.isEmpty
              ? 'Override removido. Feche e abra o PDV novamente para voltar ao padrão.'
              : 'URL salva. Feche e abra o PDV novamente para conectar nela.',
        ),
        duration: const Duration(seconds: 5),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AppDialog(
      scrollable: true,
      maxWidth: 528,
      title: Row(
        children: [
          const Icon(Icons.settings_outlined),
          const SizedBox(width: 10),
          const Expanded(child: Text('URL da API')),
          IconButton(
            tooltip: 'Fechar',
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.close),
          ),
        ],
      ),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Normalmente essa URL já vem configurada no instalador. Use '
                'isso só se o terminal não tiver sido configurado, ou pra '
                'apontar temporariamente pra outro ambiente.',
                style: TextStyle(
                  fontSize: 12.5,
                  color: scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller: _urlController,
                autofocus: true,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'URL da API',
                  hintText: 'https://api.seu-dominio.com/api/v1',
                  border: OutlineInputBorder(),
                ),
                validator: _validateUrl,
                onFieldSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 8),
              Text(
                'Deixe em branco e salve pra voltar a usar a configuração padrão.',
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          onPressed: _saving ? null : _save,
          icon: _saving
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.check),
          label: const Text('Salvar'),
        ),
      ],
    );
  }
}
