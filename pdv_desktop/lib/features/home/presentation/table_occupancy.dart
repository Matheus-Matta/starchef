/// O estado da mesa, numa regra só para todas as telas que o desenham.
///
/// CADA TELA TINHA A SUA, e elas discordavam: a grade de mesas somava a coluna
/// `status` do servidor com a contagem de cartões, o seletor lia só a coluna, e
/// o detalhe olhava só os cartões. Uma mesa com `occupied` velho no banco
/// aparecia **Ocupada** na lista e **Disponível** ao abrir — sobre a mesma mesa,
/// na mesma tela, com um clique de diferença.
///
/// A regra é a que o próprio cabeçalho da grade anuncia: a mesa fica ocupada
/// enquanto houver comanda vinculada. `reserved` e `cleaning` continuam vindo
/// do campo — são decisão de pessoa, não consequência do consumo.
library;

/// Tem cartão sentado nesta mesa?
bool tableIsOccupied(Map<String, dynamic> table) =>
    (table['active_commands'] as List? ?? const []).isNotEmpty;

/// O rótulo do estado, na ordem em que ele importa para quem olha o salão.
String tableStatusLabel(Map<String, dynamic> table) {
  if (tableIsOccupied(table)) return 'Ocupada';
  return switch ('${table['status']}') {
    'reserved' => 'Reservada',
    'cleaning' => 'Em limpeza',
    _ => 'Livre',
  };
}
