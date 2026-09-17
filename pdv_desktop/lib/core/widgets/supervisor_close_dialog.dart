import 'dart:async';

import 'package:flutter/material.dart';

import 'app_dialog.dart';

/// Autorização por **senha de ações do caixa** — a única credencial que o PDV
/// pede para liberar uma ação protegida (fechar o aplicativo, cancelar um
/// pedido, fechar a Balança Rápida).
///
/// Já houve aqui um segundo modo, "login de administrador": usuário + senha
/// validados na Retaguarda. Ele saiu de propósito. A senha do caixa é do
/// restaurante, é conferida neste terminal contra o hash já sincronizado
/// (`CashAuthRepository.verify`) e por isso funciona sem internet — o login
/// de administrador não, e no salão a pergunta "qual usuário?" travava o
/// operador na frente do cliente. Um caminho só, que sempre responde.
Future<bool> showSupervisorCloseDialog({
  required BuildContext context,
  required String title,
  required String description,
  required String confirmLabel,
  required Future<bool> Function(String password) verifyPassword,
  Future<void> Function()? onInvalidPassword,
  String cancelLabel = 'Manter aberto',
  IconData confirmIcon = Icons.power_settings_new,
  String passwordLabel = 'Senha de ações do caixa',
  String invalidPasswordMessage =
      'Senha de ações do caixa incorreta. Se ela foi alterada, '
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
          onInvalidPassword: onInvalidPassword,
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
    this.onInvalidPassword,
    required this.cancelLabel,
    required this.confirmIcon,
    required this.passwordLabel,
    required this.invalidPasswordMessage,
  });

  final String title;
  final String description;
  final String confirmLabel;
  final Future<bool> Function(String password) verifyPassword;
  final Future<void> Function()? onInvalidPassword;
  final String cancelLabel;
  final IconData confirmIcon;
  final String passwordLabel;
  final String invalidPasswordMessage;

  @override
  State<_SupervisorCloseDialog> createState() => _SupervisorCloseDialogState();
}

class _SupervisorCloseDialogState extends State<_SupervisorCloseDialog> {
  final _password = TextEditingController();
  String? _errorMessage;
  var _checking = false;

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    if (_checking) return;
    if (_password.text.isEmpty) {
      setState(() {
        _errorMessage = 'Informe ${widget.passwordLabel.toLowerCase()}.';
      });
      return;
    }

    setState(() {
      _checking = true;
      _errorMessage = null;
    });
    String? failure;
    try {
      final valid = await widget.verifyPassword(_password.text);
      if (!valid) failure = widget.invalidPasswordMessage;
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

  @override
  Widget build(BuildContext context) {
    return AppDialog(
      title: Row(
        children: [
          const Icon(Icons.lock_outline),
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
            const SizedBox(height: 16),
            TextField(
              key: const Key('restaurant-password'),
              controller: _password,
              autofocus: true,
              obscureText: true,
              enabled: !_checking,
              decoration: InputDecoration(
                labelText: widget.passwordLabel,
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
