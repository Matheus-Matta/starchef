import 'package:flutter/material.dart';

import '../../home/presentation/command_table_selection_dialog.dart';
import 'commands_loading.dart';

/// Sentar o cartão numa mesa — ou tirá-lo dela.
///
/// Separado de `commands_actions.dart`, que cuida do CONSUMO (lançar, enviar,
/// cancelar). Aqui é onde o cartão está no salão, não o que ele tem a cobrar:
/// duas perguntas que mudam por motivos diferentes.
mixin CommandsTableActions<T extends StatefulWidget> on CommandsLoading<T> {
  List<Map<String, dynamic>> get mesas;

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
