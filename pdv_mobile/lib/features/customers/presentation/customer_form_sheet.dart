import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/labeled_field.dart';
import '../../orders/data/orders_repository.dart';

/// Cadastro (ou edição) de cliente em uma folha, o gesto do celular.
///
/// No aparelho o teclado ocupa metade da tela, então a folha sobe com ele e o
/// formulário é curto de propósito: nome e telefone bastam para o garçom
/// registrar quem está na mesa. E-mail e CPF ficam para quem tem o dado em
/// mãos — obrigá-los faria o garçom inventar valores para conseguir salvar.
Future<Map<String, dynamic>?> showCustomerForm(
  BuildContext context,
  OrdersRepository repository, {
  Map<String, dynamic>? existing,
}) => showAppSheet<Map<String, dynamic>>(
  context,
  builder: (_) => _CustomerForm(repository: repository, existing: existing),
);

class _CustomerForm extends StatefulWidget {
  const _CustomerForm({required this.repository, this.existing});

  final OrdersRepository repository;
  final Map<String, dynamic>? existing;

  @override
  State<_CustomerForm> createState() => _CustomerFormState();
}

class _CustomerFormState extends State<_CustomerForm> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _nome;
  late final TextEditingController _telefone;
  late final TextEditingController _email;
  late final TextEditingController _documento;
  var _salvando = false;
  String _erro = '';

  bool get _editando => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final atual = widget.existing ?? const <String, dynamic>{};
    String campo(String chave) => '${atual[chave] ?? ''}';
    _nome = TextEditingController(text: campo('name'));
    _telefone = TextEditingController(text: campo('phone'));
    _email = TextEditingController(text: campo('email'));
    _documento = TextEditingController(text: campo('document'));
  }

  @override
  void dispose() {
    _nome.dispose();
    _telefone.dispose();
    _email.dispose();
    _documento.dispose();
    super.dispose();
  }

  Future<void> _salvar() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _salvando = true;
      _erro = '';
    });
    final corpo = {
      'name': _nome.text.trim(),
      'phone': _telefone.text.trim(),
      'email': _email.text.trim(),
      'document': _documento.text.trim(),
      'is_active': true,
    };
    try {
      final salvo = _editando
          ? await widget.repository.updateCustomer(
              '${widget.existing!['id']}',
              corpo,
            )
          : await widget.repository.createCustomer(corpo);
      if (!mounted) return;
      Navigator.pop(context, salvo);
    } on ApiException catch (falha) {
      if (!mounted) return;
      // A folha segue aberta com o que já foi digitado: o garçom corrige o
      // campo recusado em vez de preencher tudo de novo, em pé na frente do
      // cliente.
      setState(() {
        _erro = falha.message;
        _salvando = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return Form(
      key: _formKey,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AppSheetHeader(
            title: _editando ? 'Editar cliente' : 'Novo cliente',
            subtitle: _editando
                ? null
                : 'Nome e telefone bastam. O resto pode entrar depois.',
          ),
          const SizedBox(height: 8),
          LabeledField(
            controller: _nome,
            label: 'Nome',
            icon: Icons.person_outline,
            textInputAction: TextInputAction.next,
            validator: (value) => value == null || value.trim().isEmpty
                ? 'Informe o nome.'
                : null,
          ),
          const SizedBox(height: 12),
          LabeledField(
            controller: _telefone,
            label: 'Telefone',
            icon: Icons.phone_outlined,
            keyboardType: TextInputType.phone,
            textInputAction: TextInputAction.next,
            validator: (value) => value == null || value.trim().isEmpty
                ? 'Informe o telefone.'
                : null,
          ),
          const SizedBox(height: 12),
          LabeledField(
            controller: _email,
            label: 'E-mail (opcional)',
            icon: Icons.mail_outline,
            keyboardType: TextInputType.emailAddress,
            textInputAction: TextInputAction.next,
          ),
          const SizedBox(height: 12),
          LabeledField(
            controller: _documento,
            label: 'CPF (opcional)',
            icon: Icons.badge_outlined,
            keyboardType: TextInputType.number,
            onSubmitted: (_) => _salvar(),
          ),
          if (_erro.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_erro, style: TextStyle(color: cores.error)),
            ),
          const SizedBox(height: 18),
          FilledButton.icon(
            onPressed: _salvando ? null : _salvar,
            icon: _salvando
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.check),
            label: Text(_editando ? 'Salvar' : 'Cadastrar'),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
