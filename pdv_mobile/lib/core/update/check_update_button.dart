import 'package:flutter/material.dart';

import 'manual_update_action.dart';
import 'mobile_update_service.dart';

/// "Buscar atualização", com a versão instalada à vista.
///
/// Fica fora do menu de propósito: quem precisa dele é justamente quem não
/// recebeu o aviso automático, e esse não vai procurar num menu. A versão no
/// rótulo é o que o suporte pergunta primeiro.
class CheckUpdateButton extends StatefulWidget {
  const CheckUpdateButton({super.key, this.service});

  final MobileUpdateService? service;

  @override
  State<CheckUpdateButton> createState() => _CheckUpdateButtonState();
}

class _CheckUpdateButtonState extends State<CheckUpdateButton> {
  String _installed = '';
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final service = widget.service ?? MobileUpdateService();
    service.installedVersion().then((version) {
      if (widget.service == null) service.dispose();
      if (mounted) setState(() => _installed = version);
    });
  }

  Future<void> _check() async {
    setState(() => _busy = true);
    try {
      await checkMobileUpdateNow(context, service: widget.service);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => TextButton.icon(
    onPressed: _busy ? null : _check,
    icon: _busy
        ? const SizedBox.square(
            dimension: 18,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        : const Icon(Icons.system_update_outlined),
    label: Text(
      _installed.isEmpty
          ? 'Buscar atualização'
          : 'Buscar atualização (versão $_installed)',
    ),
  );
}
