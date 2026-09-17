import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

/// Solicita um motivo objetivo antes de cancelar um item do pedido.
class ItemVoidReasonDialog {
  static const reasons = [
    'Lançamento incorreto',
    'Cliente desistiu',
    'Item duplicado',
    'Produto indisponível',
    'Troca solicitada',
    'Outro',
  ];

  static Future<String?> show(
    BuildContext context, {
    required String itemName,
    String title = 'Remover item',
    String confirmLabel = 'Remover item',

    /// Consequência que o operador precisa saber ANTES de confirmar (ex.: que
    /// vai sair um cupom de cancelamento na cozinha). Fica em destaque, não
    /// como texto solto no meio do formulário.
    String? warning,
  }) => showDialog<String>(
    context: context,
    builder: (_) => _ItemVoidReasonForm(
      itemName: itemName,
      title: title,
      confirmLabel: confirmLabel,
      warning: warning,
    ),
  );
}

/// O formulário do motivo.
///
/// É um widget com estado porque ele é DONO do `TextEditingController`: assim
/// o descarte acontece no `dispose`, que o Flutter chama depois que a rota do
/// diálogo termina de sair. Descartar logo após `await showDialog` — que volta
/// com a animação de saída ainda rodando — deixa o campo, ainda na tela,
/// apontando para um objeto morto.
class _ItemVoidReasonForm extends StatefulWidget {
  const _ItemVoidReasonForm({
    required this.itemName,
    required this.title,
    required this.confirmLabel,
    this.warning,
  });

  final String itemName;
  final String title;
  final String confirmLabel;
  final String? warning;

  @override
  State<_ItemVoidReasonForm> createState() => _ItemVoidReasonFormState();
}

class _ItemVoidReasonFormState extends State<_ItemVoidReasonForm> {
  final _details = TextEditingController();
  var _selectedReason = ItemVoidReasonDialog.reasons.first;
  var _showDetailsError = false;

  @override
  void dispose() {
    _details.dispose();
    super.dispose();
  }

  void _confirm() {
    final details = _details.text.trim();
    if (_selectedReason == 'Outro' && details.isEmpty) {
      setState(() => _showDetailsError = true);
      return;
    }
    Navigator.pop(
      context,
      details.isEmpty ? _selectedReason : '$_selectedReason — $details',
    );
  }

  @override
  Widget build(BuildContext context) {
    final requiresDetails = _selectedReason == 'Outro';
    return AppDialog(
      scrollable: true,
      maxWidth: 488,
      title: Text(widget.title),
      content: SizedBox(
        width: 440,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.itemName,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            if (widget.warning != null) ...[
              const SizedBox(height: 14),
              _WarningBanner(message: widget.warning!),
            ],
            const SizedBox(height: 16),
            const Text('Selecione o motivo do cancelamento:'),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: ItemVoidReasonDialog.reasons
                  .map(
                    (reason) => ChoiceChip(
                      label: Text(reason),
                      selected: _selectedReason == reason,
                      onSelected: (_) => setState(() {
                        _selectedReason = reason;
                        _showDetailsError = false;
                      }),
                    ),
                  )
                  .toList(),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _details,
              autofocus: false,
              maxLength: 180,
              maxLines: 2,
              decoration: InputDecoration(
                labelText: requiresDetails
                    ? 'Descreva o motivo'
                    : 'Observação complementar (opcional)',
                hintText: 'Ex.: cliente pediu a troca do sabor',
                errorText: _showDetailsError
                    ? 'Informe o motivo do cancelamento.'
                    : null,
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Voltar'),
        ),
        FilledButton(
          onPressed: _confirm,
          child: Text(widget.confirmLabel),
        ),
      ],
    );
  }
}

class _WarningBanner extends StatelessWidget {
  const _WarningBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: scheme.errorContainer.withValues(alpha: .5),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.error.withValues(alpha: .4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.print_outlined, size: 18, color: scheme.error),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: scheme.onErrorContainer,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
