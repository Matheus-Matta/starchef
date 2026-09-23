/// O que a tela de detalhe está atendendo: um PEDIDO ou uma COMANDA.
///
/// As duas são o mesmo gesto para o garçom — abrir, ver o que já foi para a
/// cozinha, acrescentar, mandar a rodada. O que muda é o endereço no backend e
/// o fato de que a comanda não se cobra (isso é do caixa).
///
/// Existe para que a tela, o apresentador e os cartões sejam os MESMOS nos
/// dois casos. Antes a comanda tinha tela própria, e ela havia nascido pobre:
/// sem a separação "já na cozinha / a enviar / não aceitos", sem rascunho,
/// sem os selos da fila offline. Quem alterna entre os dois no turno
/// reaprendia a tela no meio do salão.
library;

enum SubjectKind { order, command }

class OrderSubject {
  const OrderSubject.order(this.id) : kind = SubjectKind.order;
  const OrderSubject.command(this.id) : kind = SubjectKind.command;

  final SubjectKind kind;
  final String id;

  bool get isCommand => kind == SubjectKind.command;

  /// Comanda não se cobra no aparelho: quem fecha a conta é o caixa, que puxa
  /// as anotações pendentes para um pedido. Um botão de receber aqui
  /// convidaria o garçom a fechar a conta de uma mesa que ainda come.
  bool get canBeCharged => !isCommand;

  @override
  bool operator ==(Object other) =>
      other is OrderSubject && other.kind == kind && other.id == id;

  @override
  int get hashCode => Object.hash(kind, id);
}

/// A comanda da LISTAGEM, lida como um pedido da listagem.
///
/// `/commands/` não traz os itens de cada cartão — traz a CONTAGEM de
/// anotações pendentes e quanto elas somam. É de propósito: desenhar um salão
/// com dezenas de comandas abertas custaria uma consulta por cartão.
///
/// Por isso o cartão da lista recebe a contagem por fora ([itemCountOf]), em
/// vez de derivá-la de uma lista de itens que não veio.
Map<String, dynamic> commandRowAsSubject(Map<String, dynamic> command) => {
  'id': command['id'],
  'status': 'open',
  'order_type': 'command',
  'command_number': command['number'],
  'command': command['id'],
  'table': command['current_table'],
  'table_number': command['current_table_number'],
  'customer_name': command['customer_name'],
  'total': command['pending_total'],
  'items': const <Map<String, dynamic>>[],
};

/// Quantas anotações pendentes a comanda tem, segundo a listagem.
int itemCountOf(Map<String, dynamic> command) =>
    int.tryParse('${command['pending_items'] ?? 0}') ?? 0;

/// Remove da tela cartões que o backend ainda marcou como ocupados, mas que
/// já não possuem consumo a cobrar. Isso também protege bases antigas cujo
/// campo `status` ficou desatualizado depois do fechamento da conta.
List<Map<String, dynamic>> commandsWithPendingItems(
  Iterable<Map<String, dynamic>> commands,
) => commands
    .where((command) => itemCountOf(command) > 0)
    .toList(growable: false);

/// Uma anotação pertence ao uso atual enquanto ainda estiver pendente.
///
/// Backend antigo não enviava `command_status`; nesse caso o item continua
/// visível para não apagar consumo válido durante uma atualização gradual.
bool isCurrentCommandItem(Map<String, dynamic> item) =>
    '${item['command_status'] ?? 'pending'}' == 'pending';

/// A comanda lida como o pedido é lido.
///
/// `/commands/{id}/items/` devolve `{command, items}`; a tela de detalhe lê um
/// pedido. Isto converte um no outro — e não é disfarce: o backend serializa a
/// anotação com os MESMOS campos do item de pedido de propósito (`status`,
/// `quantity`, `total_price`…), porque as duas coisas são o mesmo consumo.
///
/// O `total` é o pendente, não o histórico: é o que a comanda deve AGORA, que
/// é a pergunta do garçom. E `status` fica `open` porque comanda não tem
/// estado de cobrança — é o que mantém o botão de receber fora da tela.
Map<String, dynamic> commandAsSubject(Map<String, dynamic> response) {
  final command = switch (response['command']) {
    final Map raw => Map<String, dynamic>.from(raw),
    _ => <String, dynamic>{},
  };
  final items = switch (response['items']) {
    final List raw =>
      raw
          .whereType<Map>()
          .map(Map<String, dynamic>.from)
          .where(isCurrentCommandItem)
          .toList(growable: false),
    _ => const <Map<String, dynamic>>[],
  };
  return {
    'id': command['id'],
    'status': 'open',
    'order_type': 'command',
    'command_number': command['number'],
    // O id da PRÓPRIA comanda: é o que o botão de mesa usa para vincular. No
    // pedido este campo é a comanda vinculada a ele; aqui o assunto é ela
    // mesma, e a vinculação de mesa é o mesmo gesto.
    'command': command['id'],
    // O id da mesa, e não só o número: é por ele que a tela sabe se a comanda
    // já tem mesa e decide entre oferecer o vínculo e oferecer a troca.
    'table': command['current_table'],
    'table_number': command['current_table_number'],
    'customer_name': command['customer_name'],
    'total': command['pending_total'],
    'items': items,
  };
}
