import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// O cache de listas no disco: o PDV reiniciado abre com o catálogo na tela.
///
/// Sem isto, toda abertura do PDV começava com a tela de carregando até o
/// servidor responder as listas. O que volta do disco vem VELHO e é relido em
/// segundo plano — o disco só serve para a tela não abrir vazia.
///
/// Falha de disco nunca derruba nada: o cache é um extra. Arquivo corrompido é
/// ignorado; escrita que falha é tentada de novo na próxima mudança.
class DiscoDoCache {
  DiscoDoCache(this.arquivo, {this.espera = const Duration(seconds: 2)});

  final File arquivo;

  /// Junta as escritas: um pagamento marca três assuntos de uma vez, e cada
  /// marca não precisa virar uma gravação.
  final Duration espera;
  Timer? _agendada;

  void carregar<T>(
    Map<String, T> destino,
    T Function(String assunto, Map<String, dynamic> resposta, DateTime quando)
    criar,
  ) {
    try {
      if (!arquivo.existsSync()) return;
      final bruto = jsonDecode(arquivo.readAsStringSync());
      if (bruto is! Map) return;
      for (final MapEntry(:key, :value) in bruto.entries) {
        if (value is! Map) continue;
        final quando = DateTime.tryParse('${value['guardada_em']}');
        final resposta = value['resposta'];
        if (quando == null || resposta is! Map) continue;
        destino['$key'] = criar(
          '${value['assunto']}',
          Map<String, dynamic>.from(resposta),
          quando,
        );
      }
    } catch (_) {
      // Arquivo corrompido ou de outra versão: começa vazio, como antes.
    }
  }

  void salvar<T>(
    Map<String, T> entradas,
    Map<String, dynamic> Function(T) paraJson,
  ) {
    _agendada?.cancel();
    _agendada = Timer(espera, () {
      try {
        arquivo.parent.createSync(recursive: true);
        final temporario = File('${arquivo.path}.tmp');
        temporario.writeAsStringSync(
          jsonEncode({
            for (final MapEntry(:key, :value) in entradas.entries)
              key: paraJson(value),
          }),
        );
        // Troca atômica: um PDV desligado no meio da gravação não deixa o
        // arquivo pela metade.
        temporario.renameSync(arquivo.path);
      } catch (_) {
        // Disco cheio, sem permissão: a próxima mudança tenta de novo.
      }
    });
  }
}

/// Uma lista guardada: o assunto (para marcar velha), a resposta e quando.
class EntradaDoCache {
  EntradaDoCache(
    this.assunto,
    this.resposta,
    this.guardadaEm, {
    this.velha = false,
  });

  final String assunto;
  final Map<String, dynamic> resposta;
  final DateTime guardadaEm;

  /// Algo pode ter mudado: quem lê mostra e relê em silêncio.
  bool velha;

  Map<String, dynamic> toJson() => {
    'assunto': assunto,
    'resposta': resposta,
    'guardada_em': guardadaEm.toIso8601String(),
  };
}
