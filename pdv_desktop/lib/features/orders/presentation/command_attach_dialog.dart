import 'package:flutter/material.dart';

import 'command_attach_dialog_body.dart';

/// O QUE ESTÁ NA CONTA e o que pode entrar — num lugar só.
///
/// É só ESCOLHA: nada é enviado ao servidor aqui. Quem chamou decide o que
/// fazer com a resposta — na venda o cartão entra no rascunho, na mesa ele é
/// vinculado de verdade.
///
/// Os cartões já anexados ficavam empilhados FORA, acima do botão de anexar.
/// Numa mesa com quatro cartões o carrinho começava com quatro linhas antes do
/// primeiro produto, e "incluir" ficava longe de "retirar" — dois gestos
/// opostos em cantos diferentes da tela. Aqui em cima da lista, o operador vê
/// os dois lados da mesma decisão.
///
/// [somenteComConta] é o que separa os dois usos. Na venda, um cartão LIVRE
/// não tem nada a cobrar e anexá-lo não significa coisa alguma. Na mesa é o
/// contrário: sentar um cartão livre é justamente o gesto normal.
///
/// Devolve o que mudou: `attach` com o cartão escolhido, `detach` com o id do
/// que saiu, ou `null` se o operador só fechou.
Future<CommandAttachResult?> showCommandAttachDialog(
  BuildContext context, {
  required List<Map<String, dynamic>> commands,
  List<Map<String, dynamic>> attached = const [],
  Map<String, num> totals = const {},
  String title = 'Comandas desta conta',
  bool somenteComConta = true,
}) {
  return showDialog<CommandAttachResult>(
    context: context,
    builder: (_) => CommandAttachDialog(
      commands: commands,
      attached: attached,
      totals: totals,
      title: title,
      somenteComConta: somenteComConta,
    ),
  );
}

/// O que o diálogo decidiu.
class CommandAttachResult {
  const CommandAttachResult.attach(this.command) : detachedId = null;
  const CommandAttachResult.detach(this.detachedId) : command = null;

  final Map<String, dynamic>? command;
  final String? detachedId;

  bool get isDetach => detachedId != null;
}
