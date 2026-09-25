import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/widgets/app_sheet.dart';

/// Pede o código de quem está lançando.
///
/// Aparece uma vez por atendimento, antes do primeiro item. É teclado NUMÉRICO e
/// só aceita dígitos: num totem, "joão" e "Joao" digitados às pressas viram duas
/// pessoas diferentes no relatório, e o servidor recusa letra de qualquer forma.
///
/// NÃO TEM "CANCELAR E LANÇAR ASSIM". O restaurante ligou a exigência porque
/// quer o rastro; uma saída pela lateral faria a metade dos lançamentos não ter
/// código — e um rastro pela metade não responde nada.
Future<String?> pedirCodigoDoOperador(
  BuildContext context, {
  String atual = '',
  String assunto = '',
}) => showAppSheet<String>(
  context,
  builder: (_) => _OperatorCodeForm(atual: atual, assunto: assunto),
);

class _OperatorCodeForm extends StatefulWidget {
  const _OperatorCodeForm({required this.atual, required this.assunto});

  final String atual;

  /// "Comanda 12" ou "Pedido #308" — quem está lançando precisa saber ONDE.
  final String assunto;

  @override
  State<_OperatorCodeForm> createState() => _OperatorCodeFormState();
}

class _OperatorCodeFormState extends State<_OperatorCodeForm> {
  late final _codigo = TextEditingController(text: widget.atual);
  String _erro = '';

  @override
  void dispose() {
    _codigo.dispose();
    super.dispose();
  }

  void _confirmar() {
    final limpo = _codigo.text.replaceAll(RegExp(r'\D'), '');
    if (limpo.isEmpty) {
      setState(() => _erro = 'Informe o seu código.');
      return;
    }
    Navigator.pop(context, limpo);
  }

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppSheetHeader(
          title: 'Quem está lançando?',
          subtitle: widget.assunto.isEmpty
              ? 'Informe o seu código para registrar o lançamento.'
              : '${widget.assunto} · informe o seu código para registrar.',
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('operator-code-input'),
          controller: _codigo,
          autofocus: true,
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          maxLength: 20,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w800,
            letterSpacing: 4,
          ),
          onSubmitted: (_) => _confirmar(),
          decoration: InputDecoration(
            hintText: '0000',
            counterText: '',
            errorText: _erro.isEmpty ? null : _erro,
            border: const OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'O código fica no registro do item. Ele não é senha e não dá permissão '
          'de nada — serve para saber quem anotou.',
          style: TextStyle(fontSize: 12, color: cores.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          key: const Key('operator-code-confirm'),
          onPressed: _confirmar,
          icon: const Icon(Icons.check),
          label: const Text('Confirmar'),
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}
