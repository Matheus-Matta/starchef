import 'package:flutter/material.dart';

import '../../../core/storage/local_preferences.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/copyable_error.dart';
import '../../../core/widgets/app_text_field.dart';
import '../../settings/presentation/api_url_settings_dialog.dart';
import 'auth_controller.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({
    super.key,
    required this.controller,
    required this.isDark,
    required this.onToggleTheme,
    required this.preferences,
  });

  final AuthController controller;
  final bool isDark;
  final VoidCallback onToggleTheme;
  final LocalPreferences preferences;

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

  @override
  Widget build(BuildContext context) => Scaffold(
    body: LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        return Row(
          children: [
            if (wide) const Expanded(flex: 21, child: _BrandPanel()),
            Expanded(
              flex: 20,
              child: Stack(
                children: [
                  Center(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.all(32),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 384),
                        child: _LoginForm(
                          formKey: _formKey,
                          username: _username,
                          password: _password,
                          remember: _remember,
                          hidePassword: _hidePassword,
                          controller: widget.controller,
                          onRememberChanged: (value) =>
                              setState(() => _remember = value),
                          onPasswordVisibilityChanged: () =>
                              setState(() => _hidePassword = !_hidePassword),
                          onSubmit: _submit,
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    top: 24,
                    right: 24,
                    child: Row(
                      children: [
                        IconButton.outlined(
                          tooltip: 'URL da API',
                          onPressed: () => ApiUrlSettingsDialog.show(
                            context,
                            widget.preferences,
                          ),
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
          style: Theme.of(
            context,
          ).textTheme.bodyMedium?.copyWith(color: AppColors.stone500),
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
              borderRadius: BorderRadius.circular(8),
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
        ElevatedButton.icon(
          onPressed: controller.loading ? null : onSubmit,
          icon: controller.loading
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    color: Colors.white,
                  ),
                )
              : const Icon(Icons.login),
          label: Text(controller.loading ? 'Entrando...' : 'Entrar'),
        ),
        const SizedBox(height: 24),
        Text(
          'O acesso é protegido pelos dados da sua conta StarChef.',
          textAlign: TextAlign.center,
          style: Theme.of(
            context,
          ).textTheme.bodySmall?.copyWith(color: AppColors.stone500),
        ),
      ],
    ),
  );
}

class _BrandPanel extends StatelessWidget {
  const _BrandPanel();

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(48),
    decoration: const BoxDecoration(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [AppColors.orange, AppColors.orangeDark, Color(0xFF7C2D12)],
      ),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Image.asset(
              'assets/logoicon.png',
              width: 46,
              height: 46,
              filterQuality: FilterQuality.high,
            ),
            const SizedBox(width: 12),
            const Text(
              'StarChef',
              style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
        const Spacer(),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'A cozinha e o salão, no mesmo ritmo.',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 38,
                  height: 1.1,
                  fontWeight: FontWeight.w800,
                ),
              ),
              SizedBox(height: 20),
              Text(
                'Pedidos, comandas, caixa e equipamentos locais em um só lugar para o seu restaurante.',
                style: TextStyle(
                  color: Color(0xFFffdfd0),
                  fontSize: 15,
                  height: 1.6,
                  fontWeight: FontWeight.w500,
                ),
              ),
              SizedBox(height: 28),
              Wrap(
                spacing: 28,
                runSpacing: 20,
                children: [
                  _Feature(
                    icon: Icons.receipt_long_outlined,
                    label: 'Pedidos & comandas',
                  ),
                  _Feature(
                    icon: Icons.desktop_windows_outlined,
                    label: 'KDS ao vivo',
                  ),
                  _Feature(
                    icon: Icons.payments_outlined,
                    label: 'Caixa & pagamentos',
                  ),
                ],
              ),
            ],
          ),
        ),
        const Spacer(),
        const Text(
          '© 2026 StarChef · PDV desktop',
          style: TextStyle(color: Color(0xFFffd0bb), fontSize: 12),
        ),
      ],
    ),
  );
}

class _Feature extends StatelessWidget {
  const _Feature({required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: 105,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 42,
          height: 42,
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: .16),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(icon, color: Colors.white, size: 21),
        ),
        const SizedBox(height: 9),
        Text(
          label,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12.5,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  );
}
