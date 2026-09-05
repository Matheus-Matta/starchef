import 'package:flutter/material.dart';

import '../../../core/errors/failure_text.dart';
import '../../../core/widgets/app_toast.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'command_picker_sheet.dart';
import 'new_order_sheet.dart';
import 'order_formatters.dart';
import 'table_picker_sheet.dart';

/// Abrir um pedido, da primeira pergunta ao primeiro item.
///
/// São quatro folhas em sequência (tipo → comanda → mesa → produto), cada uma
/// podendo ser cancelada e qualquer uma podendo falhar por falta de rede. Isso
/// vivia dentro do `State` da lista de pedidos, onde o caminho inteiro ficava
/// espremido entre `AppBar` e `ListView`; aqui é uma coisa só, com começo e
/// fim, e a tela só recebe o pedido pronto para abrir.
///
/// Devolve o pedido a abrir, ou `null` se o garçom desistiu no meio (ou se
/// alguma etapa falhou — nesse caso o motivo já foi mostrado a ele).
Future<Map<String, dynamic>?> startNewOrder(
  BuildContext context,
  OrdersRepository repository,
) async {
  final kind = await showNewOrderSheet(context);
  if (kind == null || !context.mounted) return null;
  if (kind == NewOrderKind.comanda) return _fromCommand(context, repository);

  final item = await showProductPicker(context, repository);
  if (item == null || !context.mounted) return null;
  return _create(context, repository, orderType: kind.orderType, item: item);
}

/// Comanda: pode já estar em atendimento, e aí o pedido é o que já existe.
///
/// Comanda ocupada é selecionável de propósito — é assim que o garçom volta a
/// uma mesa para lançar mais itens.
Future<Map<String, dynamic>?> _fromCommand(
  BuildContext context,
  OrdersRepository repository,
) async {
  final command = await showCommandPicker(context, repository);
  if (command == null || !context.mounted) return null;

  final current = fieldText(command['current_order_id']);
  if (current.isNotEmpty) return {'id': current};

  // A mesa só é perguntada quando a comanda ainda não tem uma: o vínculo é do
  // atendimento, não a forma de abrir o pedido.
  Map<String, dynamic>? table;
  if (fieldText(command['current_table']).isEmpty) {
    table = await _chooseTable(context, repository, command);
    if (!context.mounted) return null;
  }

  final item = await showProductPicker(context, repository);
  if (item == null || !context.mounted) return null;
  return _create(
    context,
    repository,
    orderType: 'command',
    item: item,
    commandId: '${command['id']}',
    tableId: table == null ? null : '${table['id']}',
  );
}

Future<Map<String, dynamic>?> _chooseTable(
  BuildContext context,
  OrdersRepository repository,
  Map<String, dynamic> command,
) async {
  final List<Map<String, dynamic>> tables;
  try {
    tables = await repository.tables();
  } catch (error) {
    if (context.mounted) showToast(context, describeFailure(error));
    return null;
  }
  if (!context.mounted) return null;
  return showTablePicker(
    context,
    tables,
    commandLabel: 'Comanda ${command['number'] ?? ''}',
  );
}

Future<Map<String, dynamic>?> _create(
  BuildContext context,
  OrdersRepository repository, {
  required String orderType,
  required ProductChoice item,
  String? commandId,
  String? tableId,
}) async {
  try {
    return await repository.createOrderWithItem(
      orderType: orderType,
      commandId: commandId,
      tableId: tableId,
      productId: item.productId,
      quantity: item.quantity,
      variationId: item.variationId,
      addonIds: item.addonIds,
      customerNote: item.note,
    );
  } catch (error) {
    if (context.mounted) showToast(context, describeFailure(error));
    return null;
  }
}
