import 'package:flutter/material.dart';

import '../../../core/config/app_config.dart';
import '../../../core/widgets/app_dialog.dart';

import '../../../core/storage/local_preferences.dart';

/// Permite digitar manualmente a URL da API pela tela de login ou pelo menu
/// Mais. É um escape hatch para quando o terminal foi instalado sem
/// `--dart-define`/`.env` (ou precisa apontar para outro ambiente). Fica salvo
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
    // O IP server local guardado (vindo da nuvem no login, ou digitado).
    // Vazio quando o terminal usa só a nuvem — nunca o endereço da nuvem.
    text: widget.preferences.ipServerLocalGuardado ?? '',
  );
  late bool _somenteNuvem = widget.preferences.somenteNuvem;
  final _formKey = GlobalKey<FormState>();
  bool _saving = false;

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  String? _validateUrl(String? value) {
    final text = _comEsquema(value?.trim() ?? '');
    if (text.isEmpty) return null; // vazio = remove o override, é válido.
    final uri = Uri.tryParse(text);
    final valid =
        uri != null &&
        (uri.scheme == 'http' || uri.scheme == 'https') &&
        uri.host.isNotEmpty;
    return valid
        ? null
        : 'Informe o IP do servidor da loja (ex.: 192.168.0.10:8000).';
  }

  /// "192.168.0.10:8000" vira "http://192.168.0.10:8000": na rede da loja o
  /// servidor fala HTTP, e ninguém digita o esquema de um IP.
  static String _comEsquema(String texto) =>
      texto.isEmpty || texto.contains('://') ? texto : 'http://$texto';

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final text = _comEsquema(_urlController.text.trim());
    await widget.preferences.setApiBaseUrlOverride(
      text.isEmpty ? null : AppConfig.normalizeApiBaseUrl(text),
    );
    await widget.preferences.setSomenteNuvem(_somenteNuvem);
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
          const Expanded(child: Text('Servidores')),
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
              // A NUVEM É FIXA: só aparece, não se digita. É por ela que o
              // login pega o IP server local do restaurante.
              InputDecorator(
                decoration: const InputDecoration(
                  labelText: 'IP server nuvem (fixo)',
                  border: OutlineInputBorder(),
                ),
                child: SelectableText(AppConfig.ipServerNuvem),
              ),
              const SizedBox(height: 8),
              // Liga no TERMINAL o que o cadastro do restaurante liga para
              // todos: o IP local fica guardado, mas ignorado.
              SwitchListTile(
                key: const ValueKey('somente-nuvem'),
                contentPadding: EdgeInsets.zero,
                value: _somenteNuvem,
                onChanged: (valor) => setState(() => _somenteNuvem = valor),
                title: const Text('Usar só a nuvem'),
                subtitle: const Text(
                  'Ignora o IP server local: este terminal entra e fica na '
                  'nuvem. Vale a partir do próximo login.',
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'O IP server local vem sozinho no login, do cadastro do '
                'restaurante na nuvem (Restaurantes > IP server local). Digite '
                'aqui só para forçar outro neste terminal.',
                style: TextStyle(
                  fontSize: 12.5,
                  color: scheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 12),
              TextFormField(
                controller: _urlController,
                autofocus: true,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'IP server local',
                  hintText: 'http://192.168.0.10:8000',
                  border: OutlineInputBorder(),
                ),
                validator: _validateUrl,
                onFieldSubmitted: (_) => _save(),
              ),
              const SizedBox(height: 8),
              Text(
                'Em branco: o terminal usa só a nuvem até o próximo login.',
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
