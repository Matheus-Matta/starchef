import 'order_draft_cart.dart';

/// Os cartões desta conta — anexar, soltar e somar.
///
/// Separado do carrinho porque são dois assuntos: o carrinho é o que está
/// sendo VENDIDO agora, e isto é de QUEM é a conta. Juntos, a classe passava a
/// ter duas razões para mudar — uma quando o lançamento muda, outra quando a
/// regra da conta agrupada muda.
extension OrderDraftCommands on OrderDraftCart {
  /// Anexa um cartão. Passar o MESMO de novo não duplica.
  ///
  /// O leitor dispara duas leituras com frequência, e transformar isso em erro
  /// — ou em duas linhas do mesmo cartão — ensinaria o operador a ignorar a
  /// tela. A mesa só é levada do PRIMEIRO cartão: ela diz onde a conta está
  /// sentada, e quatro cartões da mesma mesa apontam para a mesma.
  void attachCommand(
    Map<String, dynamic> value, {
    Map<String, dynamic>? at,
    List<Map<String, dynamic>> items = const [],
  }) {
    final id = '${value['id'] ?? ''}';
    if (id.isEmpty) return;
    if (!commands.any((atual) => '${atual['id']}' == id)) {
      commands.add(value);
    }
    if (items.isNotEmpty) commandItems[id] = items;
    table ??= at;
    orderType = 'command';
  }

  /// Guarda o que veio do servidor para um cartão já anexado.
  void setCommandItems(String commandId, List<Map<String, dynamic>> items) {
    if (commands.any((atual) => '${atual['id']}' == commandId)) {
      commandItems[commandId] = items;
    }
  }

  /// Solta UM cartão, ou todos quando não se diz qual.
  void detachCommand([String? commandId]) {
    if (commandId == null) {
      commands.clear();
      commandItems.clear();
    } else {
      commands.removeWhere((atual) => '${atual['id']}' == commandId);
      commandItems.remove(commandId);
    }
    if (commands.isEmpty) {
      table = null;
      orderType = 'counter';
    }
  }
}
