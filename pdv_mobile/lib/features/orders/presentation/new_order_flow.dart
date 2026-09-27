import 'package:flutter/material.dart';

import '../../../core/errors/failure_text.dart';
import '../../../core/widgets/app_toast.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'command_picker_sheet.dart';
import 'new_order_sheet.dart';
import 'operator_code_sheet.dart';
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

  final codigo = await _codigoDoOperador(context, repository);
  if (codigo == null || !context.mounted) return null;
  final item = await showProductPicker(context, repository);
  if (item == null || !context.mounted) return null;
  final pedido = await _create(
    context,
    repository,
    orderType: kind.orderType,
    item: item,
    codigo: codigo,
  );
  // Guardado pelo id do pedido recém-aberto: a tela de detalhe abre em
  // seguida, e sem isto ela pediria o mesmo código no item seguinte.
  if (pedido != null) {
    repository.operatorCodes.guardar('${pedido['id']}', codigo);
  }
  return pedido;
}

/// O código de quem está lançando, quando o restaurante exige.
///
/// PERGUNTA ANTES DE ENVIAR, e antes do cardápio: sem isto o garçom escolhia o
/// prato, configurava variação e adicional, e o servidor recusava o lançamento
/// inteiro por falta de um número que a tela nunca ofereceu onde digitar.
///
/// Três respostas: `''` quando o restaurante não exige (segue sem código), o
/// código digitado, e `null` quando o garçom fechou a folha — aí o fluxo
/// inteiro desiste, porque a exigência não tem saída pela lateral.
Future<String?> _codigoDoOperador(
  BuildContext context,
  OrdersRepository repository, {
  String assunto = '',
  String guardadoEm = '',
}) async {
  if (!repository.requiresOperatorCode) return '';
  final guardado = guardadoEm.isEmpty
      ? ''
      : repository.operatorCodes.codigoDe(guardadoEm);
  if (guardado.isNotEmpty) return guardado;
  final codigo = await pedirCodigoDoOperador(context, assunto: assunto);
  if (codigo == null || codigo.isEmpty) return null;
  if (guardadoEm.isNotEmpty) repository.operatorCodes.guardar(guardadoEm, codigo);
  return codigo;
}

/// O corpo que viaja com o lançamento, ou `null` quando não há código.
///
/// `null` em vez de mapa vazio: o backend distingue "não informou" de
/// "informou vazio".
Map<String, String>? _metafields(String codigo) =>
    codigo.isEmpty ? null : {OperatorCodeKeeper.chave: codigo};

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
  return {...command, '_kind': 'command'};
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
  String codigo = '',
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
      metafields: _metafields(codigo),
    );
  } catch (error) {
    if (context.mounted) showToast(context, describeFailure(error));
    return null;
  }
}
