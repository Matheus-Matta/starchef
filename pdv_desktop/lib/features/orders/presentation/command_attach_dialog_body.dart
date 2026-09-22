import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';
import '../../commands/data/command_repository.dart';
import '../../commands/presentation/command_card.dart';
import 'command_attach_attached_list.dart';
import 'command_attach_dialog.dart';

/// O corpo do diálogo de comandas. Abra-o por `showCommandAttachDialog`.
///
/// O cartão da lista é o mesmo widget da página de comandas, com as mesmas
/// cores de estado. Uma segunda aparência para a mesma coisa faria o operador
/// aprender duas leituras do mesmo salão.
class CommandAttachDialog extends StatefulWidget {
  const CommandAttachDialog({
    super.key,
    required this.commands,
    required this.attached,
    required this.totals,
    required this.title,
    required this.somenteComConta,
  });

  final List<Map<String, dynamic>> commands;
  final List<Map<String, dynamic>> attached;
  final Map<String, num> totals;
  final String title;
  final bool somenteComConta;

  @override
  State<CommandAttachDialog> createState() => _CommandAttachDialogState();
}

class _CommandAttachDialogState extends State<CommandAttachDialog> {
  final _busca = TextEditingController();
  final _foco = FocusNode(debugLabel: 'anexar-comanda');

  @override
  void dispose() {
    _busca.dispose();
    _foco.dispose();
    super.dispose();
  }

  Set<String> get _jaAnexadas =>
      widget.attached.map((c) => '${c['id']}').toSet();

  /// Os cartões que podem entrar — e que ainda não entraram.
  ///
  /// O que JÁ está na lista de cima sai daqui: ele aparece lá, com o X. Um
  /// cartão aparecendo dos dois lados faria "incluir" e "retirar" competirem
  /// pelo mesmo toque.
  List<Map<String, dynamic>> get _candidatos => widget.commands
      .where((c) => !widget.somenteComConta || comandaTemContaAberta(c))
      .where((c) => !_jaAnexadas.contains('${c['id']}'))
      .toList(growable: false);

  /// Filtra por número, código ou cliente — os três jeitos de o operador se
  /// referir ao cartão que tem na mão.
  List<Map<String, dynamic>> get _visiveis {
    final termo = _busca.text.trim().toLowerCase();
    if (termo.isEmpty) return _candidatos;
    return _candidatos
        .where(
          (comanda) => [
            '${comanda['number'] ?? ''}',
            '${comanda['code'] ?? ''}',
            '${comanda['customer_name'] ?? ''}',
          ].any((campo) => campo.toLowerCase().contains(termo)),
        )
        .toList(growable: false);
  }

  /// Ler o cartão ALTERNA: inclui se está fora, retira se já está na conta.
  ///
  /// O leitor digita o código e manda Enter. Como o cartão já anexado sai da
  /// lista de baixo, uma segunda leitura não encontraria nada — e o operador
  /// ficaria sem saber se a primeira pegou. Procurar entre os ANEXADOS antes
  /// é o que transforma o mesmo gesto físico nos dois sentidos.
  void _confirmarPelaBusca() {
    final termo = _busca.text.trim().toLowerCase();
    if (termo.isEmpty) return;

    final anexada = widget.attached.where(
      (c) => [
        '${c['number'] ?? ''}',
        '${c['code'] ?? ''}',
      ].any((campo) => campo.toLowerCase() == termo),
    );
    if (anexada.isNotEmpty) {
      _fechar(CommandAttachResult.detach('${anexada.first['id']}'));
      return;
    }

    final visiveis = _visiveis;
    if (visiveis.length == 1) {
      _fechar(CommandAttachResult.attach(visiveis.first));
    }
  }

  void _fechar(CommandAttachResult resultado) =>
      Navigator.pop(context, resultado);

  String get _vazio {
    if (widget.attached.isNotEmpty) return 'Nenhum outro cartão disponível.';
    return widget.somenteComConta
        ? 'Nenhuma comanda com conta aberta. Só entram cartões que já têm '
              'consumo lançado — um cartão livre não tem nada a cobrar.'
        : 'Nenhuma comanda disponível.';
  }

  @override
  Widget build(BuildContext context) {
    final visiveis = _visiveis;
    final scheme = Theme.of(context).colorScheme;
    return AppDialog(
      maxWidth: 560,
      title: Text(widget.title),
      content: SizedBox(
        height: 460,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            CommandAttachAttachedList(
              attached: widget.attached,
              totals: widget.totals,
              onDetach: (id) => _fechar(CommandAttachResult.detach(id)),
            ),
            // A regra fica ACIMA da busca: quem não achar o cartão precisa
            // saber que ele pode estar fora por estar livre, e não por erro de
            // digitação.
            Text(
              widget.somenteComConta
                  ? 'Só cartões com consumo lançado. Passe o mesmo cartão de '
                        'novo para retirá-lo.'
                  : 'Passe o mesmo cartão de novo para retirá-lo.',
              style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
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
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 24),
                        child: Text(_vazio, textAlign: TextAlign.center),
                      ),
                    )
                  : ListView.separated(
                      itemCount: visiveis.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 6),
                      itemBuilder: (_, indice) => CommandCard(
                        comanda: visiveis[indice],
                        ativo: false,
                        onTap: () => _fechar(
                          CommandAttachResult.attach(visiveis[indice]),
                        ),
                      ),
                    ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Fechar'),
        ),
      ],
    );
  }
}
