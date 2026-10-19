import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/data/decisoes_do_danfe.dart';

DecisaoDoDanfe resposta(String pedido, {bool imprimir = true}) =>
    DecisaoDoDanfe(
      pedidoId: pedido,
      sequencia: pedido,
      imprimir: imprimir,
      quando: DateTime(2026, 10, 18, 12),
    );

/// O registro das respostas do DANFE no balcão de verdade: caixa rápido,
/// disco ruim, arquivo apagado no meio do turno. Nada disso pode travar a
/// venda nem perder a resposta do pedido que está saindo.
void main() {
  late Directory pasta;

  setUp(() => pasta = Directory.systemTemp.createTempSync('starchef-danfe-'));
  tearDown(() => pasta.deleteSync(recursive: true));

  test(
    'caixa rápido: três vendas respondidas sem esperar o disco ficam todas',
    () async {
      // O caixa responde Enter, Esc, Enter em sequência, sem nenhuma gravação
      // terminar entre uma e outra. Gravações soltas disputariam o arquivo e a
      // última apagaria as outras.
      final arquivo = File('${pasta.path}/danfe_decisoes.json');
      final decisoes = DecisoesDoDanfe(arquivo: arquivo);

      await Future.wait([
        decisoes.registrar(resposta('101')),
        decisoes.registrar(resposta('102', imprimir: false)),
        decisoes.registrar(resposta('103')),
      ]);

      final reaberto = DecisoesDoDanfe(arquivo: arquivo);
      expect(await reaberto.imprimir('101'), isTrue);
      expect(await reaberto.imprimir('102'), isFalse);
      expect(await reaberto.imprimir('103'), isTrue);
    },
  );

  test('disco que não grava não derruba o caixa e a resposta vale', () async {
    // A "pasta" do arquivo é um ARQUIVO: criar a pasta falha, gravar falha.
    final bloqueio = File('${pasta.path}/nao_e_pasta')..writeAsStringSync('x');
    final decisoes = DecisoesDoDanfe(
      arquivo: File('${bloqueio.path}/danfe_decisoes.json'),
    );

    await decisoes.registrar(resposta('201'));

    expect(await decisoes.imprimir('201'), isTrue);
  });

  test(
    'arquivo apagado no meio do turno volta inteiro na resposta seguinte',
    () async {
      // Uma limpeza de disco (ou o técnico) apagou o arquivo com o PDV aberto.
      final arquivo = File('${pasta.path}/danfe_decisoes.json');
      final decisoes = DecisoesDoDanfe(arquivo: arquivo);
      await decisoes.registrar(resposta('301'));
      arquivo.deleteSync();

      await decisoes.registrar(resposta('302', imprimir: false));

      final reaberto = DecisoesDoDanfe(arquivo: arquivo);
      expect(await reaberto.imprimir('301'), isTrue);
      expect(await reaberto.imprimir('302'), isFalse);
    },
  );

  test('pedido nunca respondido neste terminal não vira "não"', () async {
    // `null` é "ninguém perguntou"; tratar como "não" calaria o DANFE de uma
    // venda que o caixa nem chegou a decidir.
    final decisoes = DecisoesDoDanfe(
      arquivo: File('${pasta.path}/danfe_decisoes.json'),
    );
    await decisoes.registrar(resposta('401', imprimir: false));

    expect(await decisoes.imprimir('402'), isNull);
  });
}
