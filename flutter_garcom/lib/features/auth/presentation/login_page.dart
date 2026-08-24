import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/config/app_env.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/labeled_field.dart';
import 'auth_scaffold.dart';
import 'session_controller.dart';

/// Entrada do app: só quem é o garçom.
///
/// O Caixa Principal é configurado DEPOIS, em tela própria: ele é do aparelho
/// (não do garçom), e o pareamento precisa da conta e do restaurante — que só
/// existem depois deste login.
class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.controller});

  final SessionController controller;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _formKey = GlobalKey<FormState>();
  final _username = TextEditingController();
  final _password = TextEditingController();
  bool _hidePassword = true;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (widget.controller.loading) return;
    if (!(_formKey.currentState?.validate() ?? false)) return;
    FocusScope.of(context).unfocus();
    await widget.controller.login(
      username: _username.text,
      password: _password.text,
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return AuthScaffold(
      title: 'StarChef Garçom',
      subtitle: 'Pedidos do salão, direto para o caixa.',
      error: controller.error,
      footnote: 'Retaguarda: ${AppEnv.backendUrl}',
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            LabeledField(
              controller: _username,
              label: 'Usuário',
              hint: 'seu.usuario',
              icon: Icons.person_outline,
              textInputAction: TextInputAction.next,
              autofillHints: const [AutofillHints.username],
              validator: (value) => (value == null || value.trim().isEmpty)
                  ? 'Informe o usuário.'
                  : null,
            ),
            const SizedBox(height: 14),
            LabeledField(
              controller: _password,
              label: 'Senha',
              hint: '••••••••',
              icon: Icons.lock_outline,
              obscureText: _hidePassword,
              textInputAction: TextInputAction.done,
              autofillHints: const [AutofillHints.password],
              onSubmitted: (_) => _submit(),
              validator: (value) => (value == null || value.trim().isEmpty)
                  ? 'Informe a senha.'
                  : null,
              suffix: IconButton(
                tooltip: _hidePassword ? 'Mostrar' : 'Ocultar',
                icon: Icon(
                  _hidePassword
                      ? Icons.visibility_outlined
                      : Icons.visibility_off_outlined,
                  size: 20,
                ),
                onPressed: () =>
                    setState(() => _hidePassword = !_hidePassword),
              ),
            ),
            const SizedBox(height: 20),
            ShadButton(
              onPressed: _submit,
              enabled: !controller.loading,
              height: AppTheme.controlHeight,
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
          ],
        ),
      ),
    );
  }
}
