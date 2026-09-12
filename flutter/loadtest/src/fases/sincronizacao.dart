/// Fase SINCRONIZACAO — a fila de saida escoando sob pressao.
///
/// Aqui o teste deixa de olhar a tela e passa a olhar o que acontece depois:
/// a rede volta, centenas de operacoes sobem em ordem, o id temporario vira
/// definitivo, uma parte falha de proposito e a escada de retentativa decide
/// quem volta e quem vai para revisao.
library;

import 'package:starchef_pdv/core/data/local_id.dart';

import '../metrics.dart';
import '../stack.dart';

Future<void> rodar(
  PilhaDeCarga pilha,
  Medidor medidor, {
  required List<String> pedidosCriados,
}) async {
  final antes = await pilha.fila.summary(scope: PilhaDeCarga.escopo);
  medidor.observar(
    'fila antes de sincronizar: ${antes.pending} pendentes, ${antes.failed} recusadas',
  );
  medidor.verificar(
    'a operacao inteira ficou registrada na fila enquanto nao havia rede',
    antes.pending > 0,
    detalhe: '${antes.pending} operacoes esperando',
  );

  // 1) Servidor lento: a fila nao pode travar a interface por causa disso.
  pilha.transporte
    ..online = true
    ..latencia = const Duration(milliseconds: 3)
    ..falhaTemporaria = 0.08
    ..recusaDefinitiva = 0.04;

  final relogioTotal = Stopwatch()..start();
  var ciclos = 0;
  var anterior = antes.pending + 1;
  while (ciclos < 60) {
    final resumo = await pilha.fila.summary(scope: PilhaDeCarga.escopo);
    if (resumo.pending == 0) break;
    // Sem progresso entre dois ciclos: o resto esta em backoff ou preso por
    // dependencia, e insistir so gastaria tempo do relatorio.
    if (resumo.pending >= anterior && ciclos > 3) break;
    anterior = resumo.pending;
    final relogio = Stopwatch()..start();
    // O ciclo e protegido de proposito: uma excecao escapando daqui derruba a
    // sincronizacao inteira do PDV, e isso e um ACHADO — nao motivo para o
    // teste parar antes de gerar o relatorio.
    var veredito = vOk;
    var detalhe = '';
    try {
      await pilha.sync.push(force: true);
    } catch (erro) {
      veredito = vErroInesperado;
      detalhe = 'a excecao escapou do ciclo de push: $erro';
    }
    relogio.stop();
    medidor.registrar(
      Amostra(
        'sync.ciclo_de_entrega',
        relogio.elapsedMicroseconds,
        veredito,
        caso: 'ciclo_${ciclos + 1}',
        detalhe: detalhe.isEmpty
            ? '${pilha.transporte.entregas} entregas acumuladas'
            : detalhe,
      ),
    );
    ciclos++;
  }
  relogioTotal.stop();

  final depois = await pilha.fila.summary(scope: PilhaDeCarga.escopo);
  medidor.observar(
    'escoamento levou ${relogioTotal.elapsedMilliseconds} ms em $ciclos ciclos; '
    'restaram ${depois.pending} pendentes e ${depois.failed} recusadas',
  );

  // 2) O id temporario tem de ter virado o definitivo em quem subiu.
  var promovidos = 0;
  var aindaTemporarios = 0;
  for (final pedidoId in pedidosCriados.take(80)) {
    final registro = await pilha.gateway.read('/orders/$pedidoId/');
    final identificador = '${registro['id'] ?? pedidoId}';
    if (registro['_empty'] == true) continue;
    if (LocalId.isTemporary(identificador)) {
      aindaTemporarios++;
    } else {
      promovidos++;
    }
  }
  medidor
    ..observar(
      'de ${pedidosCriados.take(80).length} pedidos conferidos, $promovidos ja usam o id do servidor '
      'e $aindaTemporarios continuam temporarios (fila ainda pendente ou recusada)',
    )
    ..verificar(
      'pedido entregue troca o id temporario pelo definitivo',
      promovidos > 0,
      detalhe: '$promovidos promovidos',
    );

  // 3) Idempotencia: reenviar a fila inteira nao pode criar nada de novo.
  final entregasAntes = pilha.transporte.entregas;
  final repeticoesAntes = pilha.transporte.repeticoesIdempotentes;
  await pilha.fila.retryAllNow(scope: PilhaDeCarga.escopo);
  try {
    await pilha.sync.push(force: true);
  } catch (erro) {
    medidor.registrar(
      Amostra('sync.ciclo_de_entrega', 0, vErroInesperado,
          caso: 'reenvio_idempotente', detalhe: '$erro'),
    );
  }
  final novasEntregas = pilha.transporte.entregas - entregasAntes;
  final novasRepeticoes = pilha.transporte.repeticoesIdempotentes - repeticoesAntes;
  medidor
    ..observar(
      'reenvio da fila: $novasEntregas operacoes novas, $novasRepeticoes devolvidas pelo recibo de idempotencia',
    )
    ..verificar(
      'reenvio nao duplica operacao ja entregue',
      novasRepeticoes >= 0 && novasEntregas <= depois.pending + depois.failed + 1,
      detalhe: '$novasEntregas novas contra ${depois.pending} pendentes',
    );

  // 4) Resposta corrompida: um proxy reverso caido devolve HTML, e o
  // `jsonDecode` estoura FormatException. O ciclo tem de sobreviver a isso —
  // uma operacao com resposta ilegivel nao pode parar a fila inteira.
  await pilha.gateway.write(
    'POST',
    '/orders/',
    body: {'restaurant': PilhaDeCarga.restauranteId, 'order_type': 'counter'},
  );
  pilha.transporte
    ..falhaTemporaria = 0
    ..recusaDefinitiva = 0
    ..respostaCorrompida = 1;
  var sobreviveu = true;
  var motivo = '';
  try {
    await pilha.sync.push(force: true);
  } catch (erro) {
    sobreviveu = false;
    motivo = '$erro';
  }
  pilha.transporte.respostaCorrompida = 0;
  medidor.verificar(
    'ciclo de sincronizacao sobrevive a resposta ilegivel do servidor',
    sobreviveu,
    detalhe: sobreviveu
        ? 'a operacao foi tratada sem derrubar o ciclo'
        : 'a excecao escapou do push e pararia a sincronizacao: $motivo',
  );

  // 5) Servidor fora do ar: a operacao volta para a fila, nao some.
  pilha.transporte
    ..online = false
    ..falhaTemporaria = 0
    ..recusaDefinitiva = 0;
  final criado = await medidor.medir(
    'escrita.abrir_pedido',
    () => pilha.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': PilhaDeCarga.restauranteId, 'order_type': 'counter'},
    ),
    caso: 'servidor_fora',
  );
  await pilha.sync.push(force: true);
  final comServidorFora = await pilha.fila.summary(scope: PilhaDeCarga.escopo);
  medidor.verificar(
    'venda feita com o servidor fora fica na fila em vez de falhar',
    criado != null && comServidorFora.pending > 0,
    detalhe: '${comServidorFora.pending} pendentes com a rede desligada',
  );
  pilha.transporte.online = true;
}
