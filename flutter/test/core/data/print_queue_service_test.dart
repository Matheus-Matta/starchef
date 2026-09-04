import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/print_queue_service.dart';

import 'pdv_test_support.dart';

/// **A fila de impressão é do terminal, não do servidor** (§17).
///
/// Antes ela vivia no backend: o agente perguntava `/print-jobs/` e imprimia o
/// que viesse. Com a internet fora não havia o que perguntar e nada saía no
/// papel — nem um cupom montado aqui mesmo. E uma impressora sem papel
/// simplesmente engolia o trabalho, porque não existia nada guardando o que
/// faltava imprimir.
void main() {
  late TestPdvStack stack;
  late PrintQueueService queue;
  const scope = TestPdvStack.scope;

  final printer = {
    'id': 'impressora-1',
    'name': 'Cozinha',
    'connection_type': 'network',
    'host': '192.168.0.50',
    'port': 9100,
  };

  setUp(() async {
    stack = await TestPdvStack.create();
    queue = stack.gateway.printQueue;
  });

  tearDown(() async => stack.dispose());

  Future<String> enfileirar({
    String content = 'COMANDA',
    String? remoteJobId,
    String jobType = 'kitchen',
  }) => queue.enqueue(
    scope: scope,
    printer: printer,
    jobType: jobType,
    content: content,
    remoteJobId: remoteJobId,
  );

  test('o cupom espera na fila até a impressora aceitar', () async {
    await enfileirar();

    final job = await queue.claimNext(scope: scope);

    expect(job, isNotNull);
    expect(job!.content, 'COMANDA');
    expect(job.printer['host'], '192.168.0.50');
    expect(job.status, PrintJobStatus.printing);
  });

  test('falha de impressora devolve o trabalho para a fila, não o perde', () async {
    // É a diferença que dá nome a este arquivo: antes, uma impressora sem
    // papel simplesmente engolia a comanda.
    await enfileirar();
    final job = await queue.claimNext(scope: scope);

    await queue.markRetry(
      job!.id,
      attempts: 1,
      error: 'Impressora sem papel.',
    );

    final entries = await queue.entries(scope: scope);
    expect(entries.single.status, PrintJobStatus.pending);
    expect(entries.single.attempts, 1);
    expect(entries.single.nextRetryAt, isNotNull);
    expect(entries.single.lastError, contains('papel'));
  });

  test('a espera cresce a cada tentativa, sem repetir o degrau', () {
    // Começa em segundos (papel, cabo, impressora desligada se resolvem
    // assim) e vai afrouxando: passados alguns minutos, insistir no mesmo
    // ritmo não resolve e ainda custa um tempo limite por rodada.
    expect(PrintQueueService.backoffFor(1), const Duration(seconds: 5));
    expect(PrintQueueService.backoffFor(2), const Duration(seconds: 10));
    expect(
      PrintQueueService.backoffFor(PrintQueueService.maximumAttempts),
      const Duration(minutes: 15),
    );
    var previous = Duration.zero;
    for (var attempt = 1;
        attempt <= PrintQueueService.maximumAttempts;
        attempt++) {
      final wait = PrintQueueService.backoffFor(attempt);
      expect(
        wait,
        greaterThan(previous),
        reason: 'a tentativa $attempt deveria esperar mais que a anterior',
      );
      previous = wait;
    }
  });

  test('o cupom para depois de 15 tentativas e espera uma decisão', () async {
    // Sem teto, um trabalho que ninguém vai conseguir imprimir girava até
    // expirar em 12 h, custando um tempo limite por rodada e atrasando os
    // cupons bons atrás dele.
    await enfileirar();
    final job = await queue.claimNext(scope: scope);

    final antes = await queue.markRetry(
      job!.id,
      attempts: PrintQueueService.maximumAttempts - 1,
      error: 'Impressora sem resposta.',
    );
    expect(antes.exhausted, isFalse);
    expect(antes.nextRetryAt, isNotNull);

    final esgotou = await queue.markRetry(
      job.id,
      attempts: PrintQueueService.maximumAttempts,
      error: 'Impressora sem resposta.',
    );

    expect(esgotou.exhausted, isTrue);
    expect(esgotou.nextRetryAt, isNull);
    final entry = (await queue.entries(scope: scope)).single;
    expect(entry.status, PrintJobStatus.failed);
    expect(entry.attempts, PrintQueueService.maximumAttempts);
    expect(entry.lastError, contains('15 tentativas'));
    // Parou de girar sozinho: nenhuma rodada volta a reclamá-lo.
    expect(await queue.claimNext(scope: scope), isNull);
  });

  test('tentar agora devolve as 15 tentativas ao cupom esgotado', () async {
    // O operador resolveu a causa; a contagem recomeça, senão o botão da tela
    // da fila daria uma única tentativa e o cupom voltaria a travar.
    await enfileirar();
    final job = await queue.claimNext(scope: scope);
    await queue.markRetry(
      job!.id,
      attempts: PrintQueueService.maximumAttempts,
      error: 'Impressora sem resposta.',
    );

    await queue.retryNow(job.id);

    final entry = (await queue.entries(scope: scope)).single;
    expect(entry.status, PrintJobStatus.pending);
    expect(entry.attempts, 0);
  });

  test('trabalho em espera não é reclamado antes da hora', () async {
    await enfileirar();
    final job = await queue.claimNext(scope: scope);
    await queue.markRetry(job!.id, attempts: 1, error: 'Sem papel.');

    expect(await queue.claimNext(scope: scope), isNull);

    // Quando a impressora volta, o operador (ou o próprio agente) antecipa.
    await queue.retryAllNow(scope: scope);
    expect(await queue.claimNext(scope: scope), isNotNull);
  });

  test('reserva impede que duas janelas imprimam o mesmo cupom', () async {
    // O PDV e a Balança Rápida compartilham o banco: sem reserva, o papel
    // sairia duas vezes.
    await enfileirar();

    final primeira = await queue.claimNext(scope: scope);
    final segunda = await queue.claimNext(scope: scope);

    expect(primeira, isNotNull);
    expect(segunda, isNull);
  });

  test('o mesmo trabalho do servidor não entra duas vezes', () async {
    // Enquanto o `mark-printed` não é aceito, o job continua "pending" lá e
    // volta a aparecer na consulta seguinte.
    await enfileirar(remoteJobId: 'job-1');
    await enfileirar(remoteJobId: 'job-1');

    expect(await queue.entries(scope: scope), hasLength(1));
    expect(
      await queue.containsRemote(scope: scope, remoteJobId: 'job-1'),
      isTrue,
    );
  });

  test('impresso fica aguardando confirmação do servidor', () async {
    await enfileirar(remoteJobId: 'job-1');
    final job = await queue.claimNext(scope: scope);

    await queue.markPrinted(job!.id);

    // O papel saiu; o servidor ainda não sabe. E o trabalho NÃO volta a ser
    // impresso — quem garante isso é este estado, que sobrevive a fechar o
    // PDV (antes vivia só na memória do processo).
    expect(await queue.claimNext(scope: scope), isNull);
    final aguardando = await queue.awaitingConfirmation(scope: scope);
    expect(aguardando.single.remoteJobId, 'job-1');

    await queue.forget(aguardando.single.id);
    expect(await queue.awaitingConfirmation(scope: scope), isEmpty);
  });

  test('erro definitivo sai da rotação e fica visível para revisão', () async {
    await enfileirar();
    final job = await queue.claimNext(scope: scope);

    await queue.markFailed(job!.id, error: 'Impressora sem endereço.');

    final failed = await queue.entries(scope: scope, onlyFailed: true);
    expect(failed.single.status, PrintJobStatus.failed);
    expect(await queue.claimNext(scope: scope), isNull);

    // Depois de o operador resolver a causa, volta para a fila.
    await queue.retryFailed(failed.single.id);
    expect(await queue.claimNext(scope: scope), isNotNull);
  });

  test('cupom velho demais não sai no papel', () async {
    // Uma comanda de ontem saindo hoje confunde a cozinha mais do que ajuda.
    await enfileirar();
    final vencido = DateTime.now()
        .toUtc()
        .subtract(PrintQueueService.expiresAfter + const Duration(hours: 1));
    await stack.database.execute(
      'UPDATE print_queue SET created_at = ?',
      [vencido.toIso8601String()],
    );

    expect(await queue.claimNext(scope: scope), isNull);
    final entries = await queue.entries(scope: scope);
    expect(entries.single.status, PrintJobStatus.failed);
    expect(entries.single.lastError, contains('expirado'));
  });

  test('o resumo alimenta o indicador da tela', () async {
    await enfileirar();
    await enfileirar(content: 'RECIBO', jobType: 'receipt');
    final job = await queue.claimNext(scope: scope);
    await queue.markFailed(job!.id, error: 'Sem endereço.');

    final summary = await queue.summary(scope: scope);

    expect(summary.pending, 1);
    expect(summary.failed, 1);
    expect(summary.hasWork, isTrue);
  });

  test('a fila não cresce sem fim com o que já foi impresso', () async {
    await enfileirar();
    final job = await queue.claimNext(scope: scope);
    await queue.markPrinted(job!.id);
    await stack.database.execute(
      "UPDATE print_queue SET printed_at = ? WHERE id = ?",
      [
        DateTime.now().toUtc().subtract(const Duration(days: 1)).toIso8601String(),
        job.id,
      ],
    );

    await queue.purgeConfirmed(scope: scope);

    final row = await stack.database.querySingle(
      'SELECT COUNT(*) AS total FROM print_queue',
    );
    expect(row!['total'], 0);
  });

  test('terminais de contas diferentes não veem a fila um do outro', () async {
    await enfileirar();

    expect(
      await queue.claimNext(scope: 'starchef.test|outra-conta:operador-9'),
      isNull,
    );
  });

  group('painel da fila: tentar agora e descartar', () {
    test('tentar agora antecipa a espera e esquece a tentativa anterior', () async {
      // O operador trocou o papel: esperar a escada de retentativa recomeçar
      // do zero não faz sentido, a causa da falha mudou.
      final jobId = await enfileirar();
      final job = await queue.claimNext(scope: scope);
      await queue.markRetry(job!.id, attempts: 3, error: 'sem papel');
      expect(await queue.claimNext(scope: scope), isNull);

      await queue.retryNow(job.id);

      final reclaimed = await queue.claimNext(scope: scope);
      expect(reclaimed, isNotNull);
      expect(reclaimed!.jobId, jobId);
      expect(reclaimed.attempts, 0);
      expect(reclaimed.lastError, isNull);
    });

    test('descartar tira o cupom da fila para sempre', () async {
      await enfileirar();
      final job = await queue.claimNext(scope: scope);

      await queue.discard(job!.id);

      expect(await queue.entries(scope: scope), isEmpty);
      final resumo = await queue.summary(scope: scope);
      expect(resumo.total, 0);
    });

    test('a listagem do painel traz o que ainda não saiu no papel', () async {
      await enfileirar(content: 'COMANDA 1');
      final segundo = await enfileirar(content: 'COMANDA 2');
      final job = await queue.claimNext(scope: scope);
      await queue.markPrinted(job!.id);

      final listadas = await queue.entries(scope: scope);

      expect(listadas.map((item) => item.jobId), [segundo]);
    });

    test('limpar a fila descarta tudo que ainda espera', () async {
      // Descartar um a um não é opção com a fila cheia no balcão — que é
      // exatamente o estado de um terminal que herdou trabalho alheio.
      await enfileirar(content: 'COMANDA 1');
      await enfileirar(content: 'COMANDA 2');
      await enfileirar(content: 'COMANDA 3');

      final removidos = await queue.clearPending(scope: scope);

      expect(removidos, 3);
      expect(await queue.entries(scope: scope), isEmpty);
      expect((await queue.summary(scope: scope)).total, 0);
    });

    test('limpar a fila preserva o registro do que já saiu no papel', () async {
      // A linha `PRINTED` de um trabalho do servidor é o que impede o mesmo
      // cupom de entrar de novo na fila na próxima consulta. Apagá-la aqui
      // transformaria "limpar a fila" em "imprimir tudo de novo em seguida".
      final impresso = await enfileirar(remoteJobId: 'remoto-1');
      final job = await queue.claimNext(scope: scope);
      await queue.markPrinted(job!.id);
      await enfileirar(content: 'AINDA ESPERANDO');

      final removidos = await queue.clearPending(scope: scope);

      expect(removidos, 1);
      expect(
        await queue.containsRemote(scope: scope, remoteJobId: 'remoto-1'),
        isTrue,
        reason: 'o trabalho $impresso ja saiu e nao pode voltar a fila',
      );
    });
  });

  group('trabalho herdado de outro papel', () {
    test('entra parado, sem ir para a impressora sozinho', () async {
      // Um terminal que vira Caixa Principal encontra no servidor os
      // `PrintJob` que o principal anterior deixou pendentes — inclusive os
      // das notas que ele mesmo já imprimiu enquanto era secundário.
      // Enfileirá-los como PENDING mandava tudo para o papel de uma vez.
      await queue.enqueue(
        scope: scope,
        printer: printer,
        jobType: 'weigh_ticket',
        content: 'NOTA DE PESAGEM',
        remoteJobId: 'remoto-herdado',
        heldReason: 'Ja estava pendente quando este terminal assumiu.',
      );

      expect(await queue.claimNext(scope: scope), isNull);

      final listadas = await queue.entries(scope: scope);
      expect(listadas.single.status, PrintJobStatus.failed);
      expect(listadas.single.lastError, contains('assumiu'));
    });

    test('sai no papel quando o operador manda tentar', () async {
      await queue.enqueue(
        scope: scope,
        printer: printer,
        jobType: 'weigh_ticket',
        content: 'NOTA DE PESAGEM',
        remoteJobId: 'remoto-herdado',
        heldReason: 'Ja estava pendente quando este terminal assumiu.',
      );
      final retido = (await queue.entries(scope: scope)).single;

      await queue.retryNow(retido.id);

      final job = await queue.claimNext(scope: scope);
      expect(job, isNotNull);
      expect(job!.content, 'NOTA DE PESAGEM');
    });
  });
}
