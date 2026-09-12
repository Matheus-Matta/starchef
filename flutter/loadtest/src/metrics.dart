/// Medicao das operacoes do PDV: latencia, veredito e orcamento por operacao.
///
/// A pergunta que este arquivo responde nao e "quantas operacoes por segundo".
/// E: **o operador esperou?** Toda operacao tem um ORCAMENTO de tempo; passar
/// dele e um defeito de experiencia, mesmo que nada tenha quebrado.
library;

import 'dart:math' as math;

/// Vereditos possiveis de uma operacao medida.
const vOk = 'ok';
const vRecusaCorreta = 'recusa_correta';
const vLixoAceito = 'lixo_aceito';
const vErroInesperado = 'erro_inesperado';
const vTravou = 'travou';

const defeitos = <String>{vLixoAceito, vErroInesperado, vTravou};

/// Quanto tempo cada operacao pode levar antes de o operador perceber.
///
/// Os numeros vem da natureza da operacao, nao de medicao: escrita local e um
/// INSERT + um INSERT na fila na MESMA transacao; leitura de detalhe e uma
/// consulta por chave primaria. Passar disso significa que alguma coisa esta
/// varrendo tabela, serializando JSON grande demais ou esperando lock.
class Orcamento {
  const Orcamento(this.p95Ms, {this.travaMs = 0});

  final int p95Ms;

  /// Amostra isolada acima disto e considerada travamento da interface.
  int get limiteDeTravamento => travaMs > 0 ? travaMs : p95Ms * 10;
  final int travaMs;

  static const padrao = Orcamento(150);

  static const porOperacao = <String, Orcamento>{
    'leitura.catalogo': Orcamento(150),
    'leitura.pedido': Orcamento(60),
    'leitura.lista_pedidos': Orcamento(200),
    'leitura.caixa_atual': Orcamento(60),
    'escrita.abrir_pedido': Orcamento(80),
    'escrita.lancar_item': Orcamento(80),
    'escrita.enviar_cozinha': Orcamento(120),
    'escrita.fechar_pedido': Orcamento(120),
    'escrita.receber': Orcamento(120),
    'escrita.cancelar_item': Orcamento(80),
    'escrita.abrir_caixa': Orcamento(100),
    'escrita.movimento_caixa': Orcamento(80),
    'escrita.fechar_caixa': Orcamento(150),
    'escrita.checkout_balanca': Orcamento(200),
    'fila.resumo': Orcamento(80),
    'fila.reservar': Orcamento(60),
    'impressao.enfileirar': Orcamento(60),
    'impressao.reservar': Orcamento(60),
    'render.cupom': Orcamento(20),
    'render.comanda': Orcamento(20),
    'sync.entregar_uma': Orcamento(120),
    'sync.pagina_recebida': Orcamento(400),
    // Um ciclo entrega ate 20 operacoes, cada uma com a latencia de rede que a
    // PROPRIA fase injeta, mais a escada de retentativa. O numero aqui nao
    // mede o PDV: mede o cenario. Fica folgado de proposito — o que diz se o
    // terminal esta rapido sao as operacoes unitarias, acima.
    'sync.ciclo_de_entrega': Orcamento(15000, travaMs: 60000),
    'balanca.ciclo_hands_free': Orcamento(50),
    'topologia.leitura_local': Orcamento(250),
    'topologia.escrita_local': Orcamento(300),
  };

  static Orcamento de(String operacao) => porOperacao[operacao] ?? padrao;
}

class Amostra {
  Amostra(this.operacao, this.microsegundos, this.veredito, {this.caso = 'valido', this.detalhe = ''});

  final String operacao;
  final int microsegundos;
  final String veredito;
  final String caso;
  final String detalhe;

  double get ms => microsegundos / 1000.0;
}

class ResumoOperacao {
  ResumoOperacao(this.operacao);

  final String operacao;
  final List<int> _duracoes = [];
  final Map<String, int> vereditos = {};
  final List<Amostra> problemas = [];
  int total = 0;

  void registrar(Amostra amostra) {
    total++;
    _duracoes.add(amostra.microsegundos);
    vereditos[amostra.veredito] = (vereditos[amostra.veredito] ?? 0) + 1;
    if (defeitos.contains(amostra.veredito) && problemas.length < 10) {
      problemas.add(amostra);
    }
  }

  double _percentil(double fracao) {
    if (_duracoes.isEmpty) return 0;
    final ordenado = [..._duracoes]..sort();
    final indice = ((ordenado.length - 1) * fracao).round();
    return ordenado[indice] / 1000.0;
  }

  double get p50 => _percentil(0.50);
  double get p95 => _percentil(0.95);
  double get p99 => _percentil(0.99);
  double get maximo => _duracoes.isEmpty ? 0 : _duracoes.reduce(math.max) / 1000.0;
  double get media => _duracoes.isEmpty ? 0 : _duracoes.reduce((a, b) => a + b) / _duracoes.length / 1000.0;

  Orcamento get orcamento => Orcamento.de(operacao);
  bool get estourouOrcamento => p95 > orcamento.p95Ms;

  Map<String, Object?> paraJson() => {
    'operacao': operacao,
    'total': total,
    'p50_ms': p50.toStringAsFixed(1),
    'p95_ms': p95.toStringAsFixed(1),
    'p99_ms': p99.toStringAsFixed(1),
    'max_ms': maximo.toStringAsFixed(1),
    'orcamento_p95_ms': orcamento.p95Ms,
    'estourou_orcamento': estourouOrcamento,
    'vereditos': vereditos,
  };
}

class Medidor {
  final Map<String, ResumoOperacao> operacoes = {};
  final List<Map<String, Object?>> verificacoes = [];
  final List<String> observacoes = [];

  void registrar(Amostra amostra) {
    operacoes.putIfAbsent(amostra.operacao, () => ResumoOperacao(amostra.operacao)).registrar(amostra);
  }

  /// Cronometra uma operacao e ja aplica o veredito.
  ///
  /// [esperaFalha] inverte a expectativa: e o caminho do dado invalido, em que
  /// a recusa e o comportamento certo e o sucesso e que e defeito.
  Future<T?> medir<T>(
    String operacao,
    Future<T> Function() acao, {
    bool esperaFalha = false,
    String caso = 'valido',
  }) async {
    final relogio = Stopwatch()..start();
    try {
      final resultado = await acao();
      relogio.stop();
      final veredito = esperaFalha ? vLixoAceito : _porTempo(operacao, relogio);
      registrar(Amostra(operacao, relogio.elapsedMicroseconds, veredito, caso: caso));
      return resultado;
    } catch (erro) {
      relogio.stop();
      final veredito = esperaFalha ? vRecusaCorreta : vErroInesperado;
      registrar(Amostra(
        operacao,
        relogio.elapsedMicroseconds,
        veredito,
        caso: caso,
        detalhe: erro.toString(),
      ));
      return null;
    }
  }

  String _porTempo(String operacao, Stopwatch relogio) =>
      relogio.elapsedMilliseconds > Orcamento.de(operacao).limiteDeTravamento ? vTravou : vOk;

  void verificar(String nome, bool passou, {String detalhe = ''}) {
    verificacoes.add({'nome': nome, 'ok': passou, 'detalhe': detalhe});
  }

  void observar(String texto) => observacoes.add(texto);

  int get totalAmostras => operacoes.values.fold(0, (soma, o) => soma + o.total);

  int contar(String veredito) =>
      operacoes.values.fold(0, (soma, o) => soma + (o.vereditos[veredito] ?? 0));

  List<ResumoOperacao> get lentas =>
      operacoes.values.where((o) => o.estourouOrcamento).toList()
        ..sort((a, b) => (b.p95 - b.orcamento.p95Ms).compareTo(a.p95 - a.orcamento.p95Ms));
}
