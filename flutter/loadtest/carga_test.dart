/// Teste de carga do PDV Flutter — execucao MANUAL.
///
/// Ele mora fora de `test/` de proposito: `flutter test` sem argumento (o que o
/// CI roda) nao o encontra. Para dispara-lo:
///
/// ```powershell
/// flutter test loadtest/ --dart-define=PERFIL=pesado
/// flutter test loadtest/ --dart-define=PERFIL=medio --dart-define=FASES=venda,sync
/// ```
///
/// O que ele exercita e o NUCLEO REAL do PDV: o mesmo SQLite, a mesma fila de
/// saida, o mesmo gateway offline-first, a mesma maquina da Balanca Rapida e a
/// mesma fila de impressao que rodam no balcao. So a rede e substituida — por
/// um transporte que este arquivo controla, para poder desligar, atrasar e
/// recusar sob comando.
library;

import 'package:flutter_test/flutter_test.dart';

import 'src/chaos.dart';
import 'src/config.dart';
import 'src/fases/balanca.dart' as fase_balanca;
import 'src/fases/caixa.dart' as fase_caixa;
import 'src/fases/catalogo.dart' as fase_catalogo;
import 'src/fases/impressao.dart' as fase_impressao;
import 'src/fases/sincronizacao.dart' as fase_sync;
import 'src/fases/venda.dart' as fase_venda;
import 'src/metrics.dart';
import 'src/report.dart';
import 'src/scenario.dart';
import 'src/stack.dart';

void main() {
  final config = ConfigCarga.doAmbiente();

  test(
    'carga do PDV: catalogo, venda, caixa, balanca, impressao e sincronizacao',
    () async {
      final relogio = Stopwatch()..start();
      final medidor = Medidor();
      final baralho = Baralho(config.semente);
      final pilha = await PilhaDeCarga.criar();

      // ignore: avoid_print
      void log(String mensagem) => print('[carga] $mensagem');

      log('perfil ${config.perfil.nome} | semente ${config.semente}');
      log('semeando o catalogo local (${config.perfil.registrosPorTipo} produtos)...');
      final cenario = await semear(
        pilha,
        registrosPorTipo: config.perfil.registrosPorTipo,
        baralho: baralho,
      );

      // A rede comeca desligada: tudo o que as fases fizerem tem de funcionar
      // offline e ficar na fila. E a promessa central do PDV.
      pilha.transporte.online = false;

      final pedidos = <String>[];
      try {
        if (config.rodaFase('catalogo')) {
          log('fase catalogo: ${config.perfil.leituras} leituras');
          await fase_catalogo.rodar(
            pilha, cenario, medidor, baralho,
            leituras: config.perfil.leituras,
          );
        }

        if (config.rodaFase('venda')) {
          log('fase venda: ${config.perfil.vendas} vendas completas');
          final vendas = await fase_venda.rodar(
            pilha, cenario, medidor, baralho,
            vendas: config.perfil.vendas,
            proporcaoCaos: config.proporcaoCaos,
          );
          pedidos.addAll(vendas.map((v) => v.pedidoId));
        }

        if (config.rodaFase('caixa')) {
          log('fase caixa: turno completo com movimentacoes');
          await fase_caixa.rodar(
            pilha, cenario, medidor, baralho,
            movimentos: 10 + config.perfil.vendas ~/ 10,
            proporcaoCaos: config.proporcaoCaos,
          );
        }

        if (config.rodaFase('balanca')) {
          log('fase balanca: ${config.perfil.pesagens} pesagens hands-free');
          await fase_balanca.rodar(
            pilha, cenario, medidor, baralho,
            pesagens: config.perfil.pesagens,
            proporcaoCaos: config.proporcaoCaos,
          );
        }

        if (config.rodaFase('impressao')) {
          log('fase impressao: ${config.perfil.cupons} cupons');
          await fase_impressao.rodar(
            pilha, cenario, medidor, baralho,
            cupons: config.perfil.cupons,
          );
        }

        if (config.rodaFase('sync')) {
          log('fase sincronizacao: a rede volta e a fila escoa');
          await fase_sync.rodar(pilha, medidor, pedidosCriados: pedidos);
        }

        // O banco tem de continuar integro depois de tudo isso.
        final integridade = await pilha.banco.query('PRAGMA quick_check;');
        final resultado = '${integridade.isEmpty ? '' : integridade.first.values.first}';
        medidor.verificar(
          'SQLite integro depois da carga',
          resultado == 'ok',
          detalhe: 'quick_check=$resultado',
        );
      } finally {
        relogio.stop();
        final relatorio = Relatorio(medidor, config, relogio.elapsed);
        // ignore: avoid_print
        print(relatorio.paraMarkdown());
        final arquivos = await relatorio.gravar(config.destino);
        log('relatorio: ${arquivos.first}');
        log('json .....: ${arquivos.last}');
        await pilha.descartar();
      }

      // A carga so "passa" quando nada quebrou, nada travou e nenhuma
      // verificacao de coerencia reprovou. Lentidao aparece no relatorio.
      expect(
        medidor.contar(vErroInesperado),
        0,
        reason: 'operacoes estouraram excecao inesperada — veja o relatorio',
      );
      expect(
        medidor.contar(vTravou),
        0,
        reason: 'operacoes passaram do limite de travamento — veja o relatorio',
      );
      expect(
        medidor.verificacoes.where((v) => v['ok'] == false).toList(),
        isEmpty,
        reason: 'verificacoes de coerencia reprovaram — veja o relatorio',
      );
    },
    timeout: const Timeout(Duration(minutes: 30)),
  );
}
