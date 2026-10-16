import 'package:flutter/material.dart';

import '../data/linhas_da_comanda.dart';

/// Os três jeitos de pôr uma linha na comanda da pesagem.
///
/// * **Item**: um produto do cardápio (o nome vem do cadastro);
/// * **Título**: um nome digitado, sem produto — "Coca-Cola", "Sobremesa";
/// * **Em branco**: só o traço, para escrever à mão.
///
/// Nulo desabilita todos (carregando, ou a lista chegou ao teto).
class AcoesDasLinhas extends StatelessWidget {
  const AcoesDasLinhas({
    super.key,
    required this.onItem,
    required this.onTitulo,
    required this.onEmBranco,
  });

  final VoidCallback? onItem;
  final VoidCallback? onTitulo;
  final VoidCallback? onEmBranco;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 8,
    runSpacing: 8,
    children: [
      FilledButton.tonalIcon(
        onPressed: onItem,
        icon: const Icon(Icons.add_rounded),
        label: const Text('Adicionar item'),
      ),
      OutlinedButton.icon(
        onPressed: onTitulo,
        icon: const Icon(Icons.title_rounded),
        label: const Text('Adicionar título'),
      ),
      OutlinedButton.icon(
        onPressed: onEmBranco,
        icon: const Icon(Icons.edit_note_rounded),
        label: const Text('Adicionar linha em branco'),
      ),
    ],
  );
}

/// Pede o título livre; devolve o nome (sem espaços sobrando) ou `null`.
Future<String?> pedirTituloDaLinha(BuildContext context) =>
    showDialog<String>(context: context, builder: (_) => const _TituloDialog());

class _TituloDialog extends StatefulWidget {
  const _TituloDialog();

  @override
  State<_TituloDialog> createState() => _TituloDialogState();
}

class _TituloDialogState extends State<_TituloDialog> {
  final _campo = TextEditingController();

  @override
  void dispose() {
    _campo.dispose();
    super.dispose();
  }

  void _confirmar() {
    final nome = _campo.text.split(RegExp(r'\s+')).join(' ').trim();
    if (nome.isNotEmpty) Navigator.of(context).pop(nome);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: const Text('Título da linha'),
    content: SizedBox(
      width: 380,
      child: TextField(
        controller: _campo,
        autofocus: true,
        maxLength: maximoDoTituloDaLinha,
        decoration: const InputDecoration(
          labelText: 'Ex.: Coca-Cola, Sobremesa',
          helperText: 'No papel aparecem os primeiros 14 caracteres.',
        ),
        onSubmitted: (_) => _confirmar(),
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Cancelar'),
      ),
      FilledButton(onPressed: _confirmar, child: const Text('Adicionar')),
    ],
  );
}
