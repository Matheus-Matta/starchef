import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

/// Cadastro de cliente em uma modal — a MESMA para os dois lugares que a
/// abrem.
///
/// Ela nasceu privada dentro do fluxo do pedido, onde o operador cadastra no
/// meio de uma venda de entrega. A tela de clientes precisava do mesmo
/// formulário, e copiá-lo faria os dois divergirem no primeiro campo novo:
/// um cadastro feito pela venda teria observação interna e o outro não, sem
/// nada explicando por quê.
///
/// O rótulo do botão muda com o lugar ([confirmLabel]): quem cadastra durante
/// a venda já sai com o cliente selecionado, quem cadastra na lista só
/// cadastra.
class CustomerFormDialog extends StatefulWidget {
  const CustomerFormDialog({
    super.key,
    required this.onSubmit,
    required this.onError,
    this.restaurantId,
    this.existing,
    this.confirmLabel = 'Cadastrar',
  });

  /// Grava e devolve o cliente. Quem chama decide se é `POST` ou `PATCH` — a
  /// modal não conhece rota.
  final Future<Map<String, dynamic>> Function(Map<String, dynamic> corpo)
  onSubmit;
  final void Function(Object error) onError;
  final String? restaurantId;

  /// Quando presente, a modal EDITA em vez de cadastrar.
  final Map<String, dynamic>? existing;
  final String confirmLabel;

  @override
  State<CustomerFormDialog> createState() => _CustomerFormDialogState();
}

class _CustomerFormDialogState extends State<CustomerFormDialog> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _phone;
  late final TextEditingController _email;
  late final TextEditingController _document;
  late final TextEditingController _notes;
  var _saving = false;

  @override
  void initState() {
    super.initState();
    final atual = widget.existing ?? const <String, dynamic>{};
    String campo(String chave) => '${atual[chave] ?? ''}';
    _name = TextEditingController(text: campo('name'));
    _phone = TextEditingController(text: campo('phone'));
    _email = TextEditingController(text: campo('email'));
    _document = TextEditingController(text: campo('document'));
    _notes = TextEditingController(text: campo('internal_notes'));
  }

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    _email.dispose();
    _document.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _saving = true);
    final Map<String, dynamic> customer;
    try {
      customer = await widget.onSubmit({
        if (widget.restaurantId != null) 'restaurant': widget.restaurantId,
        'name': _name.text.trim(),
        'phone': _phone.text.trim(),
        'email': _email.text.trim(),
        'document': _document.text.trim(),
        'internal_notes': _notes.text.trim(),
        'is_active': true,
      });
    } catch (error) {
      if (!mounted) return;
      widget.onError(error);
      // A modal segue aberta com o que já foi digitado: o operador corrige o
      // campo recusado em vez de preencher tudo de novo.
      setState(() => _saving = false);
      return;
    }
    if (!mounted) return;
    Navigator.pop(context, customer);
  }

  @override
  Widget build(BuildContext context) => AppDialog(
    title: Text(
      widget.existing == null ? 'Cadastrar cliente' : 'Editar cliente',
    ),
    content: SizedBox(
      width: 560,
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                controller: _name,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Nome completo',
                  helperText: 'Nome usado para identificar o cliente.',
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Informe o nome do cliente.'
                    : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Telefone',
                  helperText: 'Número para contato sobre o pedido.',
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Informe o telefone.'
                    : null,
              ),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: TextFormField(
                      controller: _email,
                      keyboardType: TextInputType.emailAddress,
                      decoration: const InputDecoration(
                        labelText: 'E-mail',
                        helperText: 'Opcional',
                      ),
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: TextFormField(
                      controller: _document,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(
                        labelText: 'CPF',
                        helperText: 'Opcional',
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _notes,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Observações internas',
                  helperText: 'Informações visíveis somente para a equipe.',
                ),
              ),
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton(
        onPressed: _saving ? null : () => Navigator.pop(context),
        child: const Text('Cancelar'),
      ),
      FilledButton.icon(
        onPressed: _saving ? null : _save,
        icon: _saving
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.save_outlined),
        label: Text(widget.confirmLabel),
      ),
    ],
  );
}
