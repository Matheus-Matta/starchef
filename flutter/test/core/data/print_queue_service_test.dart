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

  test('espera entre tentativas cresce: 5s, 15s, 30s, 1min, 2min', () {
    expect(PrintQueueService.backoffFor(1), const Duration(seconds: 5));
    expect(PrintQueueService.backoffFor(2), const Duration(seconds: 15));
    expect(PrintQueueService.backoffFor(3), const Duration(seconds: 30));
    expect(PrintQueueService.backoffFor(4), const Duration(minutes: 1));
    expect(PrintQueueService.backoffFor(5), const Duration(minutes: 2));
    // O teto se repete: insistir mais devagar não ajudaria quem espera o
    // cupom no balcão.
    expect(PrintQueueService.backoffFor(20), const Duration(minutes: 2));
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
}
