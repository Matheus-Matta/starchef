import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';
import '../../commands/data/command_repository.dart';
import '../../commands/presentation/command_card.dart';

/// Escolher a comanda que vai neste rascunho.
///
/// É só uma ESCOLHA: nada é enviado ao servidor aqui. O cartão só passa a
/// existir como pedido quando o rascunho é materializado — ao enviar à cozinha
/// ou ao ir para o pagamento.
///
/// O cartão é o mesmo widget da página de comandas, com as mesmas cores de
/// estado. Uma segunda aparência para a mesma coisa faria o operador aprender
/// duas leituras do mesmo salão.
Future<Map<String, dynamic>?> showCommandAttachDialog(
  BuildContext context, {
  required List<Map<String, dynamic>> commands,
}) {
  return showDialog<Map<String, dynamic>>(
    context: context,
    builder: (_) => _CommandAttachDialog(commands: commands),
  );
}

class _CommandAttachDialog extends StatefulWidget {
  const _CommandAttachDialog({required this.commands});

  final List<Map<String, dynamic>> commands;

  @override
  State<_CommandAttachDialog> createState() => _CommandAttachDialogState();
}

class _CommandAttachDialogState extends State<_CommandAttachDialog> {
  final _busca = TextEditingController();
  final _foco = FocusNode(debugLabel: 'anexar-comanda');

  @override
  void dispose() {
    _busca.dispose();
    _foco.dispose();
    super.dispose();
  }

  /// Só os cartões com conta aberta.
  ///
  /// Um cartão LIVRE não tem nada a cobrar, então anexá-lo a um pedido não
  /// significa coisa alguma. Some da lista em vez de aparecer e recusar ao
  /// toque: numa lista de dezenas, o que não serve só atrapalha a procura do
  /// que serve.
  List<Map<String, dynamic>> get _comAberto =>
      widget.commands.where(comandaTemContaAberta).toList(growable: false);

  /// Filtra por número, código ou cliente — os três jeitos de o operador se
  /// referir ao cartão que tem na mão.
  List<Map<String, dynamic>> get _visiveis {
    final termo = _busca.text.trim().toLowerCase();
    if (termo.isEmpty) return _comAberto;
    return _comAberto
        .where(
          (comanda) => [
            '${comanda['number'] ?? ''}',
            '${comanda['code'] ?? ''}',
            '${comanda['customer_name'] ?? ''}',
          ].any((campo) => campo.toLowerCase().contains(termo)),
        )
        .toList(growable: false);
  }

  /// Um único resultado e o operador apertou Enter: é o leitor de código de
  /// barras, que digita o código e manda Enter. Fazer ele escolher com o mouse
  /// depois de passar o cartão anularia o leitor.
  void _confirmarPelaBusca() {
    final visiveis = _visiveis;
    if (visiveis.length == 1) Navigator.pop(context, visiveis.first);
  }

  @override
  Widget build(BuildContext context) {
    final visiveis = _visiveis;
    return AppDialog(
      maxWidth: 560,
      title: const Text('Anexar comanda ao pedido'),
      content: SizedBox(
        height: 420,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // A regra fica ACIMA da busca: quem não achar o cartão precisa
            // saber que ele pode estar fora por estar livre, e não por erro de
            // digitação.
            Text(
              'Só cartões com consumo lançado.',
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
                fontSize: 12,
              ),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _busca,
              focusNode: _foco,
              autofocus: true,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.qr_code_scanner_rounded),
                hintText:
                    'Passe o cartão ou filtre por número, código, cliente',
                isDense: true,
              ),
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => _confirmarPelaBusca(),
            ),
            const SizedBox(height: 10),
            Expanded(
              child: visiveis.isEmpty
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.symmetric(horizontal: 24),
                        child: Text(
                          'Nenhuma comanda com conta aberta. Só entram '
                          'cartões que já têm consumo lançado — um cartão '
                          'livre não tem nada a cobrar.',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    )
                  : ListView.separated(
                      itemCount: visiveis.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 6),
                      itemBuilder: (_, indice) => CommandCard(
                        comanda: visiveis[indice],
                        ativo: false,
                        onTap: () => Navigator.pop(context, visiveis[indice]),
                      ),
                    ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancelar'),
        ),
      ],
    );
  }
}
