/// Relatorio final da carga do PDV, em Markdown e JSON.
library;

import 'dart:convert';
import 'dart:io';

import 'config.dart';
import 'metrics.dart';

String _tabela(List<Map<String, Object?>> linhas, List<String> colunas) {
  if (linhas.isEmpty) return '_sem dados_';
  final buffer = StringBuffer()
    ..writeln('| ${colunas.join(' | ')} |')
    ..writeln('| ${colunas.map((_) => '---').join(' | ')} |');
  for (final linha in linhas) {
    final celulas = colunas.map(
      (coluna) => '${linha[coluna] ?? ''}'.replaceAll('|', r'\|').replaceAll('\n', ' '),
    );
    buffer.writeln('| ${celulas.join(' | ')} |');
  }
  return buffer.toString().trimRight();
}

class Relatorio {
  Relatorio(this.medidor, this.config, this.duracao);

  final Medidor medidor;
  final ConfigCarga config;
  final Duration duracao;

  List<ResumoOperacao> _ordenadas() =>
      medidor.operacoes.values.toList()..sort((a, b) => b.total.compareTo(a.total));

  Map<String, Object?> paraJson() => {
    'gerado_em': DateTime.now().toIso8601String(),
    'duracao_s': duracao.inMilliseconds / 1000.0,
    'configuracao': config.paraJson(),
    'totais': {
      'operacoes': medidor.totalAmostras,
      'ok': medidor.contar(vOk),
      'recusa_correta': medidor.contar(vRecusaCorreta),
      'lixo_aceito': medidor.contar(vLixoAceito),
      'erro_inesperado': medidor.contar(vErroInesperado),
      'travou': medidor.contar(vTravou),
      'operacoes_acima_do_orcamento': medidor.lentas.length,
    },
    'operacoes': [for (final operacao in _ordenadas()) operacao.paraJson()],
    'verificacoes': medidor.verificacoes,
    'observacoes': medidor.observacoes,
    'problemas': [
      for (final operacao in medidor.operacoes.values)
        for (final amostra in operacao.problemas)
          {
            'operacao': amostra.operacao,
            'veredito': amostra.veredito,
            'caso': amostra.caso,
            'ms': amostra.ms.toStringAsFixed(1),
            'detalhe': amostra.detalhe.length > 300
                ? amostra.detalhe.substring(0, 300)
                : amostra.detalhe,
          },
    ],
  };

  String situacao() {
    final quebras = medidor.contar(vErroInesperado) + medidor.contar(vTravou);
    final reprovadas = medidor.verificacoes.where((v) => v['ok'] == false).length;
    final lixo = medidor.contar(vLixoAceito);
    if (quebras > 0 || reprovadas > 0) {
      return 'REPROVADO — $quebras operacoes quebraram ou travaram e $reprovadas verificacoes falharam';
    }
    if (lixo > 0) {
      return 'ATENCAO — $lixo dados invalidos foram aceitos pelo nucleo local';
    }
    if (medidor.lentas.isNotEmpty) {
      return 'ATENCAO — ${medidor.lentas.length} operacoes acima do orcamento de tempo';
    }
    return 'APROVADO — nada quebrou, nada travou e toda operacao ficou no orcamento';
  }

  String paraMarkdown() {
    final dados = paraJson();
    final totais = dados['totais']! as Map<String, Object?>;
    final buffer = StringBuffer()
      ..writeln('# Carga do PDV Flutter — relatorio')
      ..writeln()
      ..writeln('**${situacao()}.**')
      ..writeln()
      ..writeln('- Gerado em: ${dados['gerado_em']}')
      ..writeln('- Duracao: ${dados['duracao_s']} s')
      ..writeln('- Operacoes medidas: **${totais['operacoes']}**')
      ..writeln('- Perfil: `${config.perfil.nome}` (proporcao de caos ${config.proporcaoCaos})')
      ..writeln()
      ..writeln('## Vereditos')
      ..writeln()
      ..writeln(
        _tabela([
          {'veredito': 'ok', 'quantidade': totais['ok']},
          {'veredito': 'recusou dado invalido (correto)', 'quantidade': totais['recusa_correta']},
          {'veredito': 'ACEITOU DADO INVALIDO', 'quantidade': totais['lixo_aceito']},
          {'veredito': 'ERRO INESPERADO', 'quantidade': totais['erro_inesperado']},
          {'veredito': 'TRAVOU (acima do limite)', 'quantidade': totais['travou']},
        ], ['veredito', 'quantidade']),
      )
      ..writeln()
      ..writeln('## Tempo por operacao')
      ..writeln()
      ..writeln('`orcamento` e o tempo maximo aceitavel no p95 daquela operacao.')
      ..writeln('Passar dele significa que o operador espera — mesmo sem nada quebrar.')
      ..writeln()
      ..writeln(
        _tabela([
          for (final operacao in _ordenadas())
            {
              'operacao': operacao.operacao,
              'n': operacao.total,
              'p50': operacao.p50.toStringAsFixed(1),
              'p95': operacao.p95.toStringAsFixed(1),
              'p99': operacao.p99.toStringAsFixed(1),
              'max': operacao.maximo.toStringAsFixed(1),
              'orcamento': operacao.orcamento.p95Ms,
              'situacao': operacao.estourouOrcamento ? 'ACIMA' : 'ok',
            },
        ], ['operacao', 'n', 'p50', 'p95', 'p99', 'max', 'orcamento', 'situacao']),
      )
      ..writeln()
      ..writeln('## Verificacoes de coerencia')
      ..writeln()
      ..writeln(
        _tabela([
          for (final verificacao in medidor.verificacoes)
            {
              'verificacao': verificacao['nome'],
              'resultado': verificacao['ok'] == true ? 'OK' : 'FALHOU',
              'detalhe': verificacao['detalhe'],
            },
        ], ['verificacao', 'resultado', 'detalhe']),
      );

    final problemas = dados['problemas']! as List;
    buffer
      ..writeln()
      ..writeln('## Problemas encontrados')
      ..writeln();
    if (problemas.isEmpty) {
      buffer.writeln(
        '_Nenhum: nenhuma excecao inesperada, nenhum travamento e nenhum dado invalido aceito._',
      );
    } else {
      for (var indice = 0; indice < problemas.length && indice < 60; indice++) {
        final problema = problemas[indice]! as Map<String, Object?>;
        buffer
          ..writeln(
            '### ${indice + 1}. [${problema['veredito']}] ${problema['operacao']} — caso `${problema['caso']}`',
          )
          ..writeln()
          ..writeln('- Tempo: ${problema['ms']} ms')
          ..writeln('- Detalhe: `${problema['detalhe']}`')
          ..writeln();
      }
    }

    if (medidor.observacoes.isNotEmpty) {
      buffer
        ..writeln()
        ..writeln('## Observacoes')
        ..writeln();
      for (final observacao in medidor.observacoes) {
        buffer.writeln('- $observacao');
      }
    }
    return buffer.toString();
  }

  Future<List<String>> gravar(String diretorio) async {
    final pasta = Directory(diretorio);
    await pasta.create(recursive: true);
    final carimbo = DateTime.now()
        .toIso8601String()
        .replaceAll(RegExp('[:.]'), '-')
        .substring(0, 19);
    final base = '${pasta.path}${Platform.pathSeparator}pdv-carga-$carimbo';
    await File('$base.json').writeAsString(
      const JsonEncoder.withIndent('  ').convert(paraJson()),
    );
    await File('$base.md').writeAsString(paraMarkdown());
    return ['$base.md', '$base.json'];
  }
}
