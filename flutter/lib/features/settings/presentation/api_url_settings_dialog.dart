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
class ApiUrlSettingsDialog extends StatefulWidget {
  const ApiUrlSettingsDialog({
    super.key,
    required this.preferences,
    required this.currentApiBaseUrl,
  });

  final LocalPreferences preferences;
  final String currentApiBaseUrl;

  static Future<bool> show(
    BuildContext context,
    LocalPreferences preferences,
    String currentApiBaseUrl,
  ) async =>
      await showDialog<bool>(
        context: context,
        builder: (_) => ApiUrlSettingsDialog(
          preferences: preferences,
          currentApiBaseUrl: currentApiBaseUrl,
        ),
      ) ??
      false;

  @override
  State<ApiUrlSettingsDialog> createState() => _ApiUrlSettingsDialogState();
}

class _ApiUrlSettingsDialogState extends State<ApiUrlSettingsDialog> {
  late final _urlController = TextEditingController(
    text: widget.preferences.apiBaseUrlOverride ?? widget.currentApiBaseUrl,
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
    Navigator.pop(context, true);
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
                'A alteração é aplicada imediatamente ao próximo login. Se '
                'você informar apenas o domínio, o app acrescenta /api/v1.',
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
                  hintText: 'https://api.starchef.com.br/api/v1',
                  border: OutlineInputBorder(),
                ),
                validator: _validateUrl,
                onFieldSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 8),
              Text(
                'Deixe em branco e salve para voltar à API oficial do StarChef.',
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
