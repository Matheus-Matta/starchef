part of 'new_order_flow.dart';

/// Comanda: o garçom ANOTA nela. Nenhum pedido é aberto.
///
/// Era `open-command`, que criava um pedido para o cartão — e era esse gesto
/// que prendia a comanda: desistir deixava um pedido vazio que alguém tinha de
/// cancelar, e a mesa continuava ocupada por ele.
///
/// Comanda ocupada é selecionável de propósito: é assim que o garçom volta a
/// uma mesa para lançar mais.
///
/// Devolve a COMANDA (não um pedido), para a tela abrir o cartão.
Future<Map<String, dynamic>?> _fromCommand(
  BuildContext context,
  OrdersRepository repository,
) async {
  final command = await showCommandPicker(context, repository);
  if (command == null || !context.mounted) return null;

  // A mesa só é perguntada quando a comanda ainda não tem uma: o vínculo é do
  // atendimento, não a forma de lançar.
  if (fieldText(command['current_table']).isEmpty) {
    final table = await _chooseTable(context, repository, command);
    if (!context.mounted) return null;
    if (table != null) {
      try {
        await repository.linkTable(
          commandId: '${command['id']}',
          tableId: '${table['id']}',
          tableLabel: '${table['number'] ?? ''}',
        );
      } catch (error) {
        if (!context.mounted) return null;
        showToast(context, describeFailure(error));
        return null;
      }
    }
  }
  // O vínculo da mesa é `await`: o contexto precisa ser conferido de novo
  // antes da folha seguinte, senão a tela pode já ter saído.
  if (!context.mounted) return null;

  final codigo = await _codigoDoOperador(
    context,
    repository,
    assunto: 'Comanda ${command['number'] ?? ''}'.trim(),
    guardadoEm: '${command['id']}',
  );
  if (codigo == null || !context.mounted) return null;

  final item = await showProductPicker(context, repository);
  if (item == null || !context.mounted) return null;
  try {
    await repository.launchCommandItem(
      commandId: '${command['id']}',
      productId: item.productId,
      productName: item.productName,
      quantity: item.quantity,
      variationId: item.variationId,
      addonIds: item.addonIds,
      customerNote: item.note,
      metafields: _metafields(codigo),
    );
  } catch (error) {
    if (context.mounted) showToast(context, describeFailure(error));
    return null;
  }
  // LANÇAR NA COMANDA JÁ MANDA PARA A PRODUÇÃO — o mesmo gesto do "Enviar".
  // Sem isto o primeiro item da comanda ficava só anotado, nenhum ticket
  // nascia, e o setor nunca recebia o pedido.
  try {
    await repository.sendCommandToKitchen('${command['id']}');
  } on MutationQueued {
    // Sem rede: o envio sobe na fila, junto com o item.
  } catch (error) {
    if (context.mounted) showToast(context, describeFailure(error));
  }
  return {...command, '_kind': 'command'};
}
