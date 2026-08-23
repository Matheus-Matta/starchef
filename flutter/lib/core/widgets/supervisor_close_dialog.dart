import 'dart:async';

import 'package:flutter/material.dart';

import 'app_dialog.dart';

Future<bool> showSupervisorCloseDialog({
  required BuildContext context,
  required String title,
  required String description,
  required String confirmLabel,
  required Future<bool> Function(String password) verifyPassword,
  Future<void> Function()? onInvalidPassword,
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
  });

  final String title;
  final String description;
  final String confirmLabel;
  final Future<bool> Function(String password) verifyPassword;
  final Future<void> Function()? onInvalidPassword;

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
    if (_checking || _password.text.isEmpty) return;

    setState(() {
      _checking = true;
      _errorMessage = null;
    });
    final valid = await widget.verifyPassword(_password.text);
    if (!mounted) return;

    if (valid) {
      Navigator.of(context).pop(true);
      return;
    }

    await widget.onInvalidPassword?.call();
    if (!mounted) return;
    setState(() {
      _checking = false;
      _errorMessage = 'Senha do Supervisor incorreta.';
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
            const SizedBox(height: 16),
            TextField(
              controller: _password,
              autofocus: true,
              obscureText: true,
              enabled: !_checking,
              decoration: InputDecoration(
                labelText: 'Senha do Supervisor',
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
          child: const Text('Manter aberto'),
        ),
        FilledButton.icon(
          onPressed: _checking ? null : () => unawaited(_confirm()),
          icon: _checking
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.power_settings_new),
          label: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}
