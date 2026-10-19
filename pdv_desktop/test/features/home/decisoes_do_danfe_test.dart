import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/data/decisoes_do_danfe.dart';

DecisaoDoDanfe decisao(String pedido, {bool imprimir = true}) => DecisaoDoDanfe(
  pedidoId: pedido,
  sequencia: '10$pedido',
  imprimir: imprimir,
  quando: DateTime(2026, 10, 18, 12),
);

void main() {
  late Directory pasta;
  late File arquivo;

  setUp(() {
    pasta = Directory.systemTemp.createTempSync('starchef-danfe-');
    arquivo = File('${pasta.path}/danfe_decisoes.json');
  });
  tearDown(() => pasta.deleteSync(recursive: true));

  test(
    'a resposta do caixa fica guardada por pedido e sobrevive a reabrir o PDV',
    () async {
      // O DANFE sai minutos depois da pergunta (a SEFAZ autoriza depois).
      // Sem registro, não havia como saber qual venda o caixa mandou
      // imprimir e qual não.
      await DecisoesDoDanfe(arquivo: arquivo).registrar(decisao('a'));
      await DecisoesDoDanfe(
        arquivo: arquivo,
      ).registrar(decisao('b', imprimir: false));

      final reaberto = DecisoesDoDanfe(arquivo: arquivo);
      expect(await reaberto.imprimir('a'), isTrue);
      expect(await reaberto.imprimir('b'), isFalse);
      expect(await reaberto.imprimir('c'), isNull);
      expect((await reaberto.ler()).first.sequencia, '10b');
    },
  );

  test(
    'responder de novo o mesmo pedido troca a resposta, sem duplicar',
    () async {
      final decisoes = DecisoesDoDanfe(arquivo: arquivo);
      await decisoes.registrar(decisao('a'));
      await decisoes.registrar(decisao('a', imprimir: false));

      expect(await decisoes.imprimir('a'), isFalse);
      expect(await decisoes.ler(), hasLength(1));
    },
  );

  test('guarda só as últimas, a mais nova primeiro', () async {
    final decisoes = DecisoesDoDanfe(arquivo: arquivo);
    for (var n = 1; n <= DecisoesDoDanfe.maximo + 5; n++) {
      await decisoes.registrar(decisao('$n'));
    }

    final lidas = await DecisoesDoDanfe(arquivo: arquivo).ler();
    expect(lidas, hasLength(DecisoesDoDanfe.maximo));
    expect(lidas.first.pedidoId, '${DecisoesDoDanfe.maximo + 5}');
  });

  test('arquivo estragado não derruba o caixa: começa vazio', () async {
    arquivo.writeAsStringSync('{isto não é json');

    expect(await DecisoesDoDanfe(arquivo: arquivo).ler(), isEmpty);
  });
}
