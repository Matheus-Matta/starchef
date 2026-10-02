import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../../devices/presentation/printer_selection_dialog.dart';
import 'command_labels.dart';
import 'command_labels_dialogs.dart';
import 'commands_loading.dart';

/// O que sobrou de um lote: quantas saíram, onde parou e por quê.
typedef ResultadoDoLote = ({int impressas, String? parouEm, String? falha});

/// Etiquetas de comanda para quem não tem cartão físico.
///
/// Escolhe-se a faixa ("da 10 à 100") e a impressora; as etiquetas saem uma a
/// uma pelo agente deste terminal, como o recibo. Falhou no meio, o lote PARA
/// e diz em qual comanda — para continuar dali, sem reimprimir as que saíram.
mixin CommandsLabels<T extends StatefulWidget> on CommandsLoading<T> {
  Future<void> Function(Map<String, dynamic> job, Map<String, dynamic> printer)?
  get imprimirNoTerminal;
  String? get restaurantIdDaTela;

  bool imprimindoEtiquetas = false;

  Future<void> imprimirEtiquetas() async {
    final imprimir = imprimirNoTerminal;
    if (imprimir == null || imprimindoEtiquetas) return;
    final numeros = [
      for (final c in comandas) int.tryParse('${c['number']}'),
    ].whereType<int>().toList()..sort();
    final faixa = await showDialog<({int de, int ate})>(
      context: context,
      builder: (_) => FaixaDeEtiquetasDialog(
        de: numeros.isEmpty ? null : numeros.first,
        ate: numeros.isEmpty ? null : numeros.last,
      ),
    );
    if (faixa == null || !mounted) return;
    setState(() {
      imprimindoEtiquetas = true;
      erro = '';
      recado = '';
    });
    try {
      final lote = await repository.inRange(
        de: faixa.de,
        ate: faixa.ate,
        restaurantId: restaurantIdDaTela,
      );
      if (!mounted) return;
      if (lote.isEmpty) {
        setState(
          () => erro =
              'Nenhuma comanda cadastrada de ${faixa.de} a ${faixa.ate}. '
              'Cadastre antes em "Criar em lote".',
        );
        return;
      }
      final impressora = await _escolherImpressora(lote.length, faixa);
      if (impressora == null || !mounted) return;
      final resultado = await _imprimirLote(lote, impressora, imprimir);
      if (!mounted) return;
      setState(() => _relatar(resultado, faixa, lote));
    } on ApiException catch (falha) {
      if (mounted) setState(() => erro = falha.message);
    } finally {
      if (mounted) setState(() => imprimindoEtiquetas = false);
    }
  }

  Future<Map<String, dynamic>?> _escolherImpressora(
    int quantas,
    ({int de, int ate}) faixa,
  ) async {
    final impressoras = await repository.printers(
      restaurantId: restaurantIdDaTela,
    );
    if (!mounted) return null;
    final escolhida = await showDialog<String>(
      context: context,
      builder: (_) => PrinterSelectionDialog(
        printers: impressoras,
        title: 'Imprimir etiquetas de comanda',
        summary: '$quantas etiquetas — da ${faixa.de} à ${faixa.ate}',
        description:
            'Número grande, QR Code e código de barras. '
            'Escolha a impressora de etiquetas.',
      ),
    );
    return impressoras.where((p) => '${p['id']}' == escolhida).firstOrNull;
  }

  void _relatar(
    ResultadoDoLote resultado,
    ({int de, int ate}) faixa,
    List<Map<String, dynamic>> lote,
  ) {
    if (resultado.falha != null) {
      erro =
          'Parou na comanda ${resultado.parouEm}: ${resultado.falha}. '
          '${resultado.impressas} saíram. Para continuar, imprima de '
          '${resultado.parouEm} a ${faixa.ate}.';
      return;
    }
    if (resultado.parouEm != null) {
      recado =
          'Parado antes da comanda ${resultado.parouEm}: '
          '${resultado.impressas} etiquetas saíram.';
      return;
    }
    final semCadastro = numerosSemCadastro(faixa.de, faixa.ate, lote);
    recado =
        '${resultado.impressas} etiquetas impressas '
        '(da ${faixa.de} à ${faixa.ate}).'
        '${semCadastro.isEmpty ? '' : ' Sem cadastro, ficaram de fora: ${listaCurta(semCadastro)}.'}';
  }

  Future<ResultadoDoLote> _imprimirLote(
    List<Map<String, dynamic>> lote,
    Map<String, dynamic> impressora,
    Future<void> Function(Map<String, dynamic>, Map<String, dynamic>) imprimir,
  ) async {
    final feitas = ValueNotifier<int>(0);
    final atual = ValueNotifier<String>('${lote.first['number']}');
    var parar = false;
    final navegador = Navigator.of(context, rootNavigator: true);
    final aberto = showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => ProgressoDasEtiquetas(
        total: lote.length,
        feitas: feitas,
        atual: atual,
        onParar: () => parar = true,
      ),
    );
    String? parouEm;
    String? falha;
    // Uma por vez, esperando cada uma: a térmica aceita uma conexão por vez,
    // e é assim que o lote sabe exatamente em que número parou.
    for (final comanda in lote) {
      final numero = '${comanda['number']}';
      if (parar) {
        parouEm = numero;
        break;
      }
      atual.value = numero;
      try {
        await imprimir(trabalhoDeEtiqueta(comanda), impressora);
        feitas.value += 1;
      } catch (e) {
        parouEm = numero;
        falha = e is ApiException ? e.message : '$e';
        break;
      }
    }
    navegador.pop();
    await aberto;
    final resultado = (impressas: feitas.value, parouEm: parouEm, falha: falha);
    feitas.dispose();
    atual.dispose();
    return resultado;
  }
}
