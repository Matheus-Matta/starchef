import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/config/app_config.dart';
import '../../../core/storage/local_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/update/pdv_update_service.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../../core/widgets/app_text_field.dart';
import '../../../core/widgets/pdv_version_indicator.dart';
import '../../settings/presentation/api_url_settings_dialog.dart';
import 'auth_controller.dart';
import 'login_brand_panel.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({
    super.key,
    required this.controller,
    required this.isDark,
    required this.onToggleTheme,
    required this.preferences,
    this.versionStatus,
    this.onClose,
  });

  final AuthController controller;
  final bool isDark;
  final VoidCallback onToggleTheme;
  final LocalPreferences preferences;
  final PdvUpdateStatus? versionStatus;
  final VoidCallback? onClose;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _remember = true;
  bool _hidePassword = true;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || widget.controller.loading) return;
    await widget.controller.login(
      username: _username.text,
      password: _password.text,
      remember: _remember,
    );
  }

  Future<void> _configureApi() async {
    final saved = await ApiUrlSettingsDialog.show(
      context,
      widget.preferences,
      widget.controller.apiBaseUrl,
    );
    if (!mounted || !saved) return;

    final config = await AppConfig.load(
      manualOverrideUrl: widget.preferences.apiBaseUrlOverride,
    );
    await widget.controller.updateApiBaseUrl(config.apiBaseUrl);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('API alterada para ${config.apiBaseUrl}.'),
        duration: const Duration(seconds: 4),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        final compact = constraints.maxWidth < 480;
        return Row(
          children: [
            if (wide) const Expanded(flex: 21, child: LoginBrandPanel()),
            Expanded(
              flex: 20,
              child: Stack(
                children: [
                  Center(
                    child: SingleChildScrollView(
                      padding: EdgeInsets.fromLTRB(
                        compact ? 16 : 32,
                        compact ? 88 : 32,
                        compact ? 16 : 32,
                        compact ? 16 : 32,
                      ),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 384),
                        child: ShadCard(
                          padding: EdgeInsets.all(compact ? 20 : 28),
                          radius: AppTheme.radius,
                          shadows: const [],
                          columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                          child: _LoginForm(
                            formKey: _formKey,
                            username: _username,
                            password: _password,
                            remember: _remember,
                            hidePassword: _hidePassword,
                            controller: widget.controller,
                            versionStatus: widget.versionStatus,
                            onRememberChanged: (value) =>
                                setState(() => _remember = value),
                            onPasswordVisibilityChanged: () =>
                                setState(() => _hidePassword = !_hidePassword),
                            onSubmit: _submit,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: compact ? 12 : 24,
                    right: compact ? 12 : 24,
                    child: Row(
                      children: [
                        IconButton.outlined(
                          tooltip: 'URL da API',
                          onPressed: _configureApi,
                          icon: const Icon(Icons.settings_outlined),
                        ),
                        const SizedBox(width: 8),
                        IconButton.outlined(
                          tooltip: 'Alternar tema',
                          onPressed: widget.onToggleTheme,
                          icon: Icon(
                            widget.isDark
                                ? Icons.light_mode_outlined
                                : Icons.dark_mode_outlined,
                          ),
                        ),
                        if (widget.onClose != null) ...[
                          const SizedBox(width: 8),
                          IconButton.outlined(
                            tooltip: 'Fechar aplicação',
                            onPressed: widget.onClose,
                            style: IconButton.styleFrom(
                              foregroundColor: Theme.of(
                                context,
                              ).colorScheme.error,
                            ),
                            icon: const Icon(Icons.power_settings_new),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    ),
  );
}

class _LoginForm extends StatelessWidget {
  const _LoginForm({
    required this.formKey,
    required this.username,
    required this.password,
    required this.remember,
    required this.hidePassword,
    required this.controller,
    required this.versionStatus,
    required this.onRememberChanged,
    required this.onPasswordVisibilityChanged,
    required this.onSubmit,
  });

  final GlobalKey<FormState> formKey;
  final TextEditingController username;
  final TextEditingController password;
  final bool remember;
  final bool hidePassword;
  final AuthController controller;
  final PdvUpdateStatus? versionStatus;
  final ValueChanged<bool> onRememberChanged;
  final VoidCallback onPasswordVisibilityChanged;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) => Form(
    key: formKey,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Bem-vindo de volta',
          style: Theme.of(
            context,
          ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Text(
          'Entre para acessar o PDV da sua filial.',
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 28),
        AppTextField(
          controller: username,
          label: 'Usuário ou e-mail',
          hint: 'manager ou você@restaurante.com',
          icon: Icons.email_outlined,
          validator: (value) => value == null || value.trim().isEmpty
              ? 'Informe o usuário ou e-mail.'
              : null,
        ),
        const SizedBox(height: 20),
        AppTextField(
          controller: password,
          label: 'Senha',
          hint: '••••••••',
          icon: Icons.lock_outline,
          obscureText: hidePassword,
          validator: (value) =>
              value == null || value.isEmpty ? 'Informe a senha.' : null,
          onSubmitted: (_) => onSubmit(),
          suffixIcon: IconButton(
            tooltip: hidePassword ? 'Mostrar senha' : 'Ocultar senha',
            onPressed: onPasswordVisibilityChanged,
            icon: Icon(
              hidePassword
                  ? Icons.visibility_outlined
                  : Icons.visibility_off_outlined,
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Switch(value: remember, onChanged: onRememberChanged),
            const SizedBox(width: 6),
            const Text('Lembrar-me'),
          ],
        ),
        if (controller.errorMessage != null) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.errorContainer,
              borderRadius: AppTheme.radius,
              border: Border.all(
                color: Theme.of(
                  context,
                ).colorScheme.error.withValues(alpha: .2),
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: SelectableText(
                    controller.errorMessage!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onErrorContainer,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Copiar erro',
                  onPressed: () => copyError(context, controller.errorMessage!),
                  icon: const Icon(Icons.copy_outlined),
                ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 20),
        ShadButton(
          onPressed: onSubmit,
          enabled: !controller.loading,
          height: 44,
          leading: controller.loading
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Icon(Icons.login, size: 18),
          child: Text(controller.loading ? 'Entrando...' : 'Entrar'),
        ),
        const SizedBox(height: 24),
        Text(
          'O acesso é protegido pelos dados da sua conta StarChef.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
        const SizedBox(height: 12),
        Center(child: PdvVersionIndicator(status: versionStatus)),
      ],
    ),
  );
}
