import 'package:flutter/material.dart';

import '../data/cash_auth_repository.dart';

/// Abre um diálogo que pede a **senha de ações do caixa** (definida no cadastro
/// do restaurante) e a verifica OFFLINE contra o hash guardado no dispositivo.
///
/// Retorna `true` se a senha for válida (ação autorizada). Funciona sem rede.
Future<bool> showCashAuthDialog(
  BuildContext context, {
  required CashAuthRepository cashAuth,
  required String restaurantId,
  String title = 'Autorização do caixa',
  String message = 'Informe a senha de ações do caixa para autorizar.',
}) async {
  final result = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _CashAuthDialog(
      cashAuth: cashAuth,
      restaurantId: restaurantId,
      title: title,
      message: message,
    ),
  );
  return result ?? false;
}

class _CashAuthDialog extends StatefulWidget {
  const _CashAuthDialog({
    required this.cashAuth,
    required this.restaurantId,
    required this.title,
    required this.message,
  });

  final CashAuthRepository cashAuth;
  final String restaurantId;
  final String title;
  final String message;

  @override
  State<_CashAuthDialog> createState() => _CashAuthDialogState();
}

class _CashAuthDialogState extends State<_CashAuthDialog> {
  final _controller = TextEditingController();
  bool _loadingConfig = true;
  bool _hasPassword = false;
  bool _checking = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final has = await widget.cashAuth.hasStoredPassword(widget.restaurantId);
    if (!mounted) return;
    setState(() {
      _hasPassword = has;
      _loadingConfig = false;
    });
  }

  Future<void> _submit() async {
    final password = _controller.text;
    if (password.isEmpty) {
      setState(() => _error = 'Informe a senha.');
      return;
    }
    setState(() {
      _checking = true;
      _error = null;
    });
    final ok = await widget.cashAuth.verify(
      password,
      restaurantId: widget.restaurantId,
    );
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop(true);
    } else {
      setState(() {
        _checking = false;
        _error = 'Senha incorreta.';
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Row(
        children: [
          const Icon(Icons.lock_outline),
          const SizedBox(width: 10),
          Expanded(child: Text(widget.title)),
        ],
      ),
      content: SizedBox(width: 420, child: _content()),
      actions: [
        TextButton(
          onPressed: _checking ? null : () => Navigator.of(context).pop(false),
          child: const Text('Cancelar'),
        ),
        if (_hasPassword)
          ElevatedButton(
            onPressed: _checking ? null : _submit,
            child: _checking
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Autorizar'),
          ),
      ],
    );
  }

  Widget _content() {
    if (_loadingConfig) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (!_hasPassword) {
      return const Text(
        'Nenhuma senha de ações do caixa está configurada para este restaurante. '
        'Defina-a no cadastro do restaurante (com rede) para permitir a autorização offline.',
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(widget.message),
        const SizedBox(height: 14),
        TextField(
          controller: _controller,
          obscureText: true,
          autofocus: true,
          enabled: !_checking,
          onSubmitted: (_) => _submit(),
          decoration: InputDecoration(
            labelText: 'Senha do caixa',
            prefixIcon: const Icon(Icons.password_outlined),
            errorText: _error,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Verificação offline — funciona mesmo sem conexão.',
          style: TextStyle(fontSize: 12, color: Colors.grey),
        ),
      ],
    );
  }
}
