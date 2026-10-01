import 'package:flutter/material.dart';

import '../../devices/presentation/printer_selection_dialog.dart';
import 'commands_loading.dart';

/// O recibo (conferência) da comanda, impresso como o recibo de venda.
///
/// Antes ele ia para a fila do servidor, na primeira impressora por nome, e
/// nunca saía. Agora segue o caminho do recibo de venda: a impressora MASTER
/// do terminal (ou a escolhida na hora) e a impressão feita aqui mesmo.
mixin CommandsReceipt<T extends StatefulWidget> on CommandsLoading<T> {
  /// A impressora master deste terminal (preferências), se houver.
  String? Function()? get impressoraMaster;

  /// Imprime um trabalho pelo agente local deste terminal.
  Future<void> Function(Map<String, dynamic> job, Map<String, dynamic> printer)?
  get imprimirNoTerminal;

  String? get restaurantIdDaTela;

  /// O botão mostra "Gerando…" enquanto o recibo sai.
  bool imprimindo = false;

  Future<void> imprimirRecibo() async {
    final id = '${selecionada?['id'] ?? ''}';
    if (id.isEmpty) return;
    setState(() {
      imprimindo = true;
      erro = '';
    });
    try {
      final imprimir = imprimirNoTerminal;
      String? escolhida;
      if (imprimir != null) {
        final impressoras = await repository.printers(
          restaurantId: restaurantIdDaTela,
        );
        if (!mounted) return;
        final master = impressoraMaster?.call();
        escolhida = impressoras.any((p) => '${p['id']}' == master)
            ? master
            : await showDialog<String>(
                context: context,
                builder: (_) => PrinterSelectionDialog(
                  printers: impressoras,
                  title: 'Imprimir recibo da comanda',
                  summary: 'Comanda ${selecionada?['number'] ?? ''}',
                  description:
                      'Itens em aberto, total e o código de barras da comanda.',
                ),
              );
        if (escolhida == null) return;
      }
      final job = await repository.receipt(
        id,
        printerId: escolhida,
        manualOnly: imprimir != null,
      );
      final printer = job['printer'];
      if (imprimir != null && printer is Map<String, dynamic>) {
        await imprimir(job, printer);
      }
      if (mounted) setState(() => recado = 'Recibo enviado para a impressora.');
    } catch (falha) {
      if (mounted) setState(() => erro = 'Falha ao imprimir o recibo: $falha');
    } finally {
      if (mounted) setState(() => imprimindo = false);
    }
  }
}
