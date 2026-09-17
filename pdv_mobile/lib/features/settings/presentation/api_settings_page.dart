import 'package:flutter/material.dart';

import '../../../core/config/api_settings.dart';
import '../../../core/widgets/labeled_field.dart';
import '../../../core/widgets/shadcn_layout.dart';

class ApiSettingsPage extends StatefulWidget {
  const ApiSettingsPage({super.key, required this.settings});

  final ApiSettings settings;

  @override
  State<ApiSettingsPage> createState() => _ApiSettingsPageState();
}

class _ApiSettingsPageState extends State<ApiSettingsPage> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _url;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: widget.settings.baseUrl);
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.settings.save(_url.text);
      if (mounted) Navigator.of(context).pop(true);
    } on FormatException catch (error) {
      setState(() => _error = error.message);
    } catch (error) {
      setState(() => _error = 'Não foi possível salvar: $error');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => AppPageScaffold(
    title: 'Servidor da API',
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text(
          'O celular se comunica diretamente com o backend. Informe o endereço '
          'completo; sem caminho, o app acrescenta /api/v1.',
        ),
        const SizedBox(height: 20),
        Form(
          key: _formKey,
          child: LabeledField(
            controller: _url,
            label: 'URL da API',
            hint: ApiSettings.defaultBaseUrl,
            icon: Icons.dns_outlined,
            keyboardType: TextInputType.url,
            validator: (value) {
              final normalized = ApiSettings.normalize(value ?? '');
              return ApiSettings.isValid(normalized)
                  ? null
                  : 'Informe uma URL HTTP ou HTTPS válida.';
            },
          ),
        ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(
            _error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        const SizedBox(height: 20),
        FilledButton.icon(
          onPressed: _saving ? null : _save,
          icon: _saving
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.save_outlined),
          label: const Text('Salvar endereço'),
        ),
        const SizedBox(height: 12),
        OutlinedButton(
          onPressed: _saving
              ? null
              : () => setState(() => _url.text = ApiSettings.defaultBaseUrl),
          child: const Text('Usar servidor padrão'),
        ),
      ],
    ),
  );
}
