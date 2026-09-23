import 'package:flutter/material.dart';

import '../../home/presentation/command_table_selection_dialog.dart';
import '../../orders/presentation/product_config_dialog.dart';
import 'command_void_dialog.dart';
import 'commands_loading.dart';

/// O que se FAZ com o cartão aberto: lançar, mandar à cozinha, imprimir,
/// cancelar uma linha e sentá-lo numa mesa.
///
/// Está fora da página pelo mesmo motivo de [CommandsLoading]: a página decide
/// em qual das duas telas se está e desenha; isto aqui conversa com o servidor.
/// Cada método termina do mesmo jeito — relê o cartão e, quando o estado dele
/// muda, relê também a grade, que é onde o operador procura "o cartão da mesa
/// 12".
mixin CommandsActions<T extends StatefulWidget> on CommandsLoading<T> {
  /// As mesas do salão, fornecidas pela página.
  List<Map<String, dynamic>> get mesas;

  List<Map<String, dynamic>> itens = const [];
  bool carregandoItens = false;
  bool enviando = false;
  bool imprimindo = false;

  Future<void> carregarItens() async {
    final id = '${selecionada?['id'] ?? ''}';
    if (id.isEmpty) return;
    setState(() {
      carregandoItens = true;
      erro = '';
    });
    try {
      final dados = await repository.items(id);
      // O operador pode ter trocado de cartão enquanto a resposta vinha.
      if (!mounted || '${selecionada?['id'] ?? ''}' != id) return;
      final bruto = dados['items'];
      setState(() {
        itens = bruto is List
            ? bruto
                  .whereType<Map>()
                  .map((item) => Map<String, dynamic>.from(item))
                  .toList()
            : const [];
      });
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao ler a comanda: $falha');
    } finally {
      if (mounted) setState(() => carregandoItens = false);
    }
  }

  /// Anota o produto NA COMANDA. Nenhum pedido é aberto.
  Future<void> lancar(
    Map<String, dynamic> produto, {
    num quantity = 1,
    String customerNote = '',
    List<String> variationIds = const [],
    List<String> addonIds = const [],
  }) async {
    final id = '${selecionada?['id'] ?? ''}';
    if (id.isEmpty) {
      setState(() => erro = 'Escolha uma comanda antes de lançar.');
      return;
    }
    try {
      await repository.launchItem(
        id,
        productId: '${produto['id']}',
        quantity: quantity,
        customerNote: customerNote,
        variationIds: variationIds,
        addonIds: addonIds,
      );
      await carregarItens();
      // A coluna da esquerda mostra o estado do cartão: o primeiro lançamento
      // o deixa ocupado, e a lista precisa acompanhar.
      await carregar();
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao lançar na comanda: $falha');
    }
  }

  Future<void> configurarProduto(Map<String, dynamic> produto) async {
    if (!productNeedsConfiguration(produto)) {
      await lancar(produto);
      return;
    }
    final configuracao = await showProductConfigDialog(context, produto);
    if (!mounted || configuracao == null) return;
    await lancar(
      produto,
      quantity: configuracao.quantity,
      customerNote: configuracao.customerNote,
      variationIds: [
        if (configuracao.variationId != null) configuracao.variationId!,
      ],
      addonIds: configuracao.addonIds,
    );
  }

  Future<void> enviarACozinha() async {
    final id = '${selecionada?['id'] ?? ''}';
    if (id.isEmpty) return;
    setState(() {
      enviando = true;
      erro = '';
    });
    try {
      final lote = await repository.sendToKitchen(id);
      await carregarItens();
      if (mounted) {
        setState(() => recado = 'Rodada ${lote['batch_number']} na cozinha.');
      }
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao enviar à cozinha: $falha');
    } finally {
      if (mounted) setState(() => enviando = false);
    }
  }

  Future<void> imprimirRecibo() async {
    final id = '${selecionada?['id'] ?? ''}';
    if (id.isEmpty) return;
    setState(() {
      imprimindo = true;
      erro = '';
    });
    try {
      await repository.receipt(id);
      if (mounted) setState(() => recado = 'Recibo enviado para a impressora.');
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao imprimir o recibo: $falha');
    } finally {
      if (mounted) setState(() => imprimindo = false);
    }
  }

  Future<void> cancelarItem(Map<String, dynamic> item) async {
    final id = '${selecionada?['id'] ?? ''}';
    final motivo = await showCommandVoidDialog(context, item: item);
    if (motivo == null || !mounted) return;
    try {
      await repository.voidItem(id, '${item['id']}', reason: motivo);
      await carregarItens();
      await carregar();
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao cancelar o item: $falha');
    }
  }

  /// Senta o cartão numa mesa — ou o tira dela.
  ///
  /// Faltava, e era o lugar natural: quem está olhando um cartão é quem sabe
  /// para qual mesa ele foi. Antes, vincular só existia no meio do fluxo de
  /// abrir pedido, então um cartão que sentou na mesa errada só era corrigido
  /// na hora de cobrar.
  Future<void> escolherMesa() async {
    final comanda = selecionada;
    if (comanda == null) return;
    final escolha = await showDialog<CommandTableSelection>(
      context: context,
      builder: (_) =>
          CommandTableSelectionDialog(command: comanda, tables: mesas),
    );
    if (escolha == null || !mounted) return;
    try {
      final id = '${comanda['id']}';
      final mesa = escolha.table;
      final atualizada = mesa == null
          ? await repository.unlinkTable(id)
          : await repository.linkTable(commandId: id, tableId: '${mesa['id']}');
      if (!mounted) return;
      // O cartão inteiro vem do servidor: trocar só o número da mesa aqui
      // deixaria a grade dizendo uma coisa e o detalhe outra.
      setState(() {
        selecionada = atualizada;
        recado = mesa == null
            ? 'Cartão tirado da mesa.'
            : 'Cartão sentado na mesa ${mesa['number']}.';
      });
      await carregar();
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao mudar a mesa: $falha');
    }
  }
}
