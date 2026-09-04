import 'dart:async';

import 'package:flutter/material.dart';

import 'app_dialog.dart';

typedef AdminCredentialVerifier =
    Future<String?> Function(String username, String password);

Future<bool> showSupervisorCloseDialog({
  required BuildContext context,
  required String title,
  required String description,
  required String confirmLabel,
  required Future<bool> Function(String password) verifyPassword,
  AdminCredentialVerifier? verifyAdminCredentials,
  Future<void> Function()? onInvalidPassword,
  String credentialRoleLabel = 'administrador',
  String cancelLabel = 'Manter aberto',
  IconData confirmIcon = Icons.power_settings_new,
  String passwordLabel = 'Senha do restaurante',
  String invalidPasswordMessage =
      'Senha do restaurante incorreta. Se ela foi alterada, '
      'recarregue os dados do PDV.',
}) async {
  return await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _SupervisorCloseDialog(
          title: title,
          description: description,
          confirmLabel: confirmLabel,
          verifyPassword: verifyPassword,
          verifyAdminCredentials: verifyAdminCredentials,
          onInvalidPassword: onInvalidPassword,
          credentialRoleLabel: credentialRoleLabel,
          cancelLabel: cancelLabel,
          confirmIcon: confirmIcon,
          passwordLabel: passwordLabel,
          invalidPasswordMessage: invalidPasswordMessage,
        ),
      ) ??
      false;
}

class _SupervisorCloseDialog extends StatefulWidget {
  const _SupervisorCloseDialog({
    required this.title,
    required this.description,
    required this.confirmLabel,
    required this.verifyPassword,
    this.verifyAdminCredentials,
    this.onInvalidPassword,
    required this.credentialRoleLabel,
    required this.cancelLabel,
    required this.confirmIcon,
    required this.passwordLabel,
    required this.invalidPasswordMessage,
  });

  final String title;
  final String description;
  final String confirmLabel;
  final Future<bool> Function(String password) verifyPassword;
  final AdminCredentialVerifier? verifyAdminCredentials;
  final Future<void> Function()? onInvalidPassword;
  final String credentialRoleLabel;
  final String cancelLabel;
  final IconData confirmIcon;
  final String passwordLabel;
  final String invalidPasswordMessage;

  @override
  State<_SupervisorCloseDialog> createState() => _SupervisorCloseDialogState();
}

class _SupervisorCloseDialogState extends State<_SupervisorCloseDialog> {
  final _username = TextEditingController();
  final _password = TextEditingController();
  String? _errorMessage;
  var _checking = false;
  var _useAdminCredentials = false;

  @override
  void dispose() {
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    if (_checking) return;
    if (_password.text.isEmpty ||
        (_useAdminCredentials && _username.text.trim().isEmpty)) {
      setState(() {
        _errorMessage = _useAdminCredentials
            ? 'Informe o usuário e a senha do ${widget.credentialRoleLabel}.'
            : 'Informe ${widget.passwordLabel.toLowerCase()}.';
      });
      return;
    }

    setState(() {
      _checking = true;
      _errorMessage = null;
    });
    String? failure;
    try {
      if (_useAdminCredentials) {
        final verifier = widget.verifyAdminCredentials;
        failure = verifier == null
            ? 'A validação por ${widget.credentialRoleLabel} não está disponível.'
            : await verifier(_username.text.trim(), _password.text);
      } else {
        final valid = await widget.verifyPassword(_password.text);
        if (!valid) {
          failure = widget.invalidPasswordMessage;
        }
      }
    } catch (_) {
      failure = 'Não foi possível validar a autorização.';
    }
    if (!mounted) return;

    if (failure == null) {
      Navigator.of(context).pop(true);
      return;
    }

    await widget.onInvalidPassword?.call();
    if (!mounted) return;
    setState(() {
      _checking = false;
      _errorMessage = failure;
      _password.clear();
    });
  }

  void _switchAuthorizationMethod() {
    if (_checking) return;
    setState(() {
      _useAdminCredentials = !_useAdminCredentials;
      _errorMessage = null;
      _password.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    return AppDialog(
      title: Row(
        children: [
          const Icon(Icons.admin_panel_settings_outlined),
          const SizedBox(width: 10),
          Expanded(child: Text(widget.title)),
        ],
      ),
      scrollable: true,
      maxWidth: 560,
      content: SizedBox(
        width: 512,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(widget.description),
            if (widget.verifyAdminCredentials != null) ...[
              const SizedBox(height: 14),
              Align(
                alignment: Alignment.centerLeft,
                child: OutlinedButton.icon(
                  onPressed: _checking ? null : _switchAuthorizationMethod,
                  icon: Icon(
                    _useAdminCredentials
                        ? Icons.storefront_outlined
                        : Icons.admin_panel_settings_outlined,
                  ),
                  label: Text(
                    _useAdminCredentials
                        ? 'Usar senha do restaurante'
                        : 'Usar login de ${widget.credentialRoleLabel}',
                  ),
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (_useAdminCredentials) ...[
              TextField(
                key: const Key('admin-username'),
                controller: _username,
                autofocus: true,
                enabled: !_checking,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Usuário ou e-mail',
                  prefixIcon: Icon(Icons.person_outline),
                ),
              ),
              const SizedBox(height: 10),
            ],
            TextField(
              key: Key(
                _useAdminCredentials ? 'admin-password' : 'restaurant-password',
              ),
              controller: _password,
              autofocus: !_useAdminCredentials,
              obscureText: true,
              enabled: !_checking,
              decoration: InputDecoration(
                labelText: _useAdminCredentials
                    ? 'Senha do ${widget.credentialRoleLabel}'
                    : widget.passwordLabel,
                prefixIcon: const Icon(Icons.lock_outline),
                errorText: _errorMessage,
              ),
              onSubmitted: (_) => unawaited(_confirm()),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _checking ? null : () => Navigator.of(context).pop(false),
          child: Text(widget.cancelLabel),
        ),
        FilledButton.icon(
          onPressed: _checking ? null : () => unawaited(_confirm()),
          icon: _checking
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Icon(widget.confirmIcon),
          label: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}
