import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';
import 'package:starchef_pdv/core/network/realtime_client.dart';
import 'package:starchef_pdv/features/devices/services/local_device_agent.dart';

import '../../../core/data/pdv_test_support.dart';

void main() {
  group('DANFE não sai duas vezes', () {
    Map<String, dynamic> danfeJob({String key = 'CHAVE-1'}) => {
      'id': 'job-1',
      'job_type': 'fiscal_danfe',
      'payload': {
        'payload_version': 2,
        'invoice_id': 'nota-1',
        'access_key': key,
        'text_content': 'DANFE NFC-e',
      },
    };

    test('a chave é da NOTA, não do trabalho de impressão', () {
      // Dois trabalhos diferentes para a mesma nota são exatamente o que fazia
      // o cliente receber duas vias idênticas.
      final first = LocalDeviceAgent.fiscalDedupeKey(danfeJob());
      final second = LocalDeviceAgent.fiscalDedupeKey({
        ...danfeJob(),
        'id': 'job-2',
      });

      expect(first, 'danfe:CHAVE-1');
      expect(second, first);
    });

    test('recibo e comanda continuam podendo sair mais de uma vez', () {
      for (final type in ['receipt', 'kitchen', 'weigh_ticket']) {
        expect(
          LocalDeviceAgent.fiscalDedupeKey({
            ...danfeJob(),
            'job_type': type,
          }),
          isNull,
          reason: type,
        );
      }
    });

    test('nota sem chave nem id não inventa identidade', () {
      expect(
        LocalDeviceAgent.fiscalDedupeKey({
          'job_type': 'fiscal_danfe',
          'payload': {'payload_version': 2, 'text_content': 'DANFE'},
        }),
        isNull,
      );
    });

    test('a marca do documento impresso sobrevive no banco local', () async {
      final stack = await TestPdvStack.create();
      addTearDown(stack.dispose);
      final queue = stack.gateway.printQueue;
      const key = 'danfe:CHAVE-1';

      expect(
        await queue.wasDocumentPrinted(
          scope: TestPdvStack.scope,
          dedupeKey: key,
        ),
        isFalse,
      );

      await queue.markDocumentPrinted(
        scope: TestPdvStack.scope,
        dedupeKey: key,
      );

      expect(
        await queue.wasDocumentPrinted(
          scope: TestPdvStack.scope,
          dedupeKey: key,
        ),
        isTrue,
      );
      // Marcar de novo não é erro: os dois caminhos (fila e impressão manual)
      // escrevem a mesma chave.
      await queue.markDocumentPrinted(
        scope: TestPdvStack.scope,
        dedupeKey: key,
      );
      expect(
        await queue.wasDocumentPrinted(
          scope: TestPdvStack.scope,
          dedupeKey: 'danfe:OUTRA',
        ),
        isFalse,
      );
    });
  });

  group('LocalDeviceAgent filtro de evento em tempo real', () {
    test('aceita PrintJob do próprio restaurante', () {
      final event = RealtimeEvent('model.updated', {
        'resource': 'printers.printjob',
        'restaurant_id': 'r1',
      });
      expect(LocalDeviceAgent.isPrintJobEvent(event, 'r1'), isTrue);
    });

    test('ignora PrintJob de outro restaurante da mesma conta', () {
      // O grupo do WS é por conta, não por restaurante: sem esse filtro o
      // agente reagiria a trabalhos de impressão de unidades que não são a
      // dele.
      final event = RealtimeEvent('model.updated', {
        'resource': 'printers.printjob',
        'restaurant_id': 'r2',
      });
      expect(LocalDeviceAgent.isPrintJobEvent(event, 'r1'), isFalse);
    });

    test('ignora eventos de outros modelos', () {
      final event = RealtimeEvent('model.updated', {
        'resource': 'orders.order',
        'restaurant_id': 'r1',
      });
      expect(LocalDeviceAgent.isPrintJobEvent(event, 'r1'), isFalse);
    });

    test('reconhece alterações de impressora e balança da unidade', () {
      for (final resource in ['printers.printer', 'printers.scale']) {
        final event = RealtimeEvent('model.updated', {
          'resource': resource,
          'restaurant_id': 'r1',
        });
        expect(
          LocalDeviceAgent.isDeviceConfigurationEvent(event, 'r1'),
          isTrue,
        );
      }
    });

    test('ignora configuração de equipamento de outra unidade', () {
      final event = RealtimeEvent('model.updated', {
        'resource': 'printers.printer',
        'restaurant_id': 'r2',
      });
      expect(LocalDeviceAgent.isDeviceConfigurationEvent(event, 'r1'), isFalse);
    });
  });

  group('LocalDeviceAgent pausas físicas padrão', () {
    test(
      'mantém uma folga padrão depois do corte, antes de liberar a porta',
      () async {
        // Sem essa folga, um segundo trabalho enfileirado logo em seguida na
        // MESMA porta (ex.: a nota de cancelamento, na impressora que acabou
        // de receber a comanda original) reabria a porta antes da guilhotina
        // terminar de atuar — o sistema aceitava os bytes sem erro nenhum,
        // mas a impressora nunca chegava a processar o segundo cupom.
        final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
        final agent = LocalDeviceAgent(api: api);
        expect(agent.postCutSettleDelay, const Duration(milliseconds: 400));
        await api.dispose();
      },
    );
  });

  group('LocalDeviceAgent fila com várias impressoras', () {
    late TestPdvStack stack;
    late Directory locks;

    setUp(() async {
      stack = await TestPdvStack.create();
      locks = await Directory.systemTemp.createTemp('starchef-drain-locks');
      AppPaths.overrideDataDirectory(locks);
    });

    tearDown(() async {
      AppPaths.overrideDataDirectory(null);
      await stack.dispose();
      try {
        await locks.delete(recursive: true);
      } on FileSystemException {
        // No Windows o arquivo de trava pode continuar preso por instantes.
      }
    });

    test(
      'uma impressora fora do ar não segura o cupom das outras',
      () async {
        // O sintoma era exatamente este: o cupom do bar travado numa térmica
        // de rede sem resposta, e a comanda da cozinha — enfileirada depois,
        // numa impressora que estava funcionando — nunca saindo, sem erro
        // nenhum na tela. A drenagem parava no primeiro que falhava.
        final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
        addTearDown(api.dispose);
        api.attachLocalStore(gateway: stack.gateway);
        final escritas = <String>[];
        final agent = LocalDeviceAgent(
          api: api,
          delay: (_) async {},
          networkWriter: (target, bytes) async {
            if (target.host == '192.0.2.99') {
              throw const SocketException('sem resposta');
            }
            escritas.add(target.host);
          },
        );
        addTearDown(agent.dispose);

        final queue = stack.gateway.printQueue;
        await queue.enqueue(
          scope: TestPdvStack.scope,
          printer: const {
            'id': 'bar',
            'name': 'Bar',
            'connection_type': 'network',
            'host': '192.0.2.99',
            'port': 9100,
          },
          jobType: 'kitchen',
          content: 'CHOPP',
        );
        await queue.enqueue(
          scope: TestPdvStack.scope,
          printer: const {
            'id': 'cozinha',
            'name': 'Cozinha',
            'connection_type': 'network',
            'host': '192.0.2.10',
            'port': 9100,
          },
          jobType: 'kitchen',
          content: 'X-BURGER',
        );

        await agent.drainPrintQueue();

        expect(escritas, ['192.0.2.10']);
        final resumo = await queue.summary(scope: TestPdvStack.scope);
        // O cupom do bar continua na fila para a próxima tentativa; o da
        // cozinha já saiu no papel.
        expect(resumo.pending, 1);
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );
  });

  group('LocalDeviceAgent confirmação de impressão', () {
    test(
      'mark-printed falhando não reimprime o mesmo trabalho no ciclo seguinte',
      () async {
        var writes = 0;
        var markPrintedAttempts = 0;
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        server.listen((request) async {
          final response = request.response;
          response.headers.contentType = ContentType.json;
          switch (request.uri.path) {
            case '/api/v1/printers/':
              response.write(
                jsonEncode({
                  'results': [
                    {
                      'id': 'printer-1',
                      'name': 'Balança',
                      'connection_type': 'network',
                      'host': '192.0.2.10',
                      'port': 9100,
                      'driver_type': 'escpos',
                      'auto_print': false,
                    },
                  ],
                }),
              );
            case '/api/v1/print-jobs/':
              final status = request.uri.queryParameters['status'];
              response.write(
                jsonEncode({
                  'results': status == 'pending'
                      ? [
                          {
                            'id': 'job-1',
                            'status': 'pending',
                            'job_type': 'weigh_ticket',
                            'printer': 'printer-1',
                            'payload': {'text_content': 'NOTA DE PESAGEM'},
                          },
                        ]
                      : const [],
                }),
              );
            case '/api/v1/print-jobs/job-1/mark-printed/':
              markPrintedAttempts++;
              if (markPrintedAttempts == 1) {
                response.statusCode = HttpStatus.internalServerError;
                response.write(jsonEncode({'detail': 'falha simulada'}));
              } else {
                response.write(jsonEncode({'ok': true}));
              }
            default:
              response.statusCode = HttpStatus.notFound;
          }
          await response.close();
        });
        addTearDown(() => server.close(force: true));

        final api = ApiClient(
          baseUrl: 'http://127.0.0.1:${server.port}/api/v1',
        );
        addTearDown(api.dispose);
        final agent = LocalDeviceAgent(
          api: api,
          networkWriter: (target, bytes) async => writes++,
        );

        await agent.processPendingPrintJobsForTesting(
          token: 'tok',
          restaurantId: 'rest-1',
        );
        expect(writes, 1, reason: 'primeiro ciclo imprime fisicamente');
        expect(markPrintedAttempts, 1);

        // mark-printed falhou no ciclo anterior: o job continua "pending" no
        // servidor de mentira e volta a aparecer aqui — sem a correção, isto
        // reimprimiria o mesmo cupom.
        await agent.processPendingPrintJobsForTesting(
          token: 'tok',
          restaurantId: 'rest-1',
        );
        expect(
          writes,
          1,
          reason: 'não reimprime; só reenvia a confirmação',
        );
        expect(markPrintedAttempts, 2);
      },
    );
  });

  group('LocalDeviceAgent ao assumir o papel de Caixa Principal', () {
    /// Servidor de mentira com o acúmulo que um Caixa Principal anterior
    /// deixou pendente.
    Future<HttpServer> servidorComBacklog({
      required String criadoEm,
      required List<int> writes,
    }) async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        final response = request.response;
        response.headers.contentType = ContentType.json;
        switch (request.uri.path) {
          case '/api/v1/printers/':
            response.write(
              jsonEncode({
                'results': [
                  {
                    'id': 'printer-1',
                    'name': 'Balança',
                    'connection_type': 'network',
                    'host': '192.0.2.10',
                    'port': 9100,
                    'driver_type': 'escpos',
                    'auto_print': false,
                  },
                ],
              }),
            );
          case '/api/v1/print-jobs/':
            final status = request.uri.queryParameters['status'];
            response.write(
              jsonEncode({
                'results': status == 'pending'
                    ? [
                        {
                          'id': 'job-antigo',
                          'status': 'pending',
                          'job_type': 'weigh_ticket',
                          'printer': 'printer-1',
                          'created_at': criadoEm,
                          'payload': {'text_content': 'NOTA DE PESAGEM'},
                        },
                      ]
                    : const [],
              }),
            );
          case '/api/v1/print-jobs/job-antigo/mark-printed/':
            response.write(jsonEncode({'ok': true}));
          default:
            response.statusCode = HttpStatus.notFound;
        }
        await response.close();
      });
      return server;
    }

    test(
      'não imprime o que já estava pendente antes da virada',
      () async {
        // O caso relatado: o terminal operou como Caixa Secundário e imprimiu
        // as notas na hora, na impressora dele. Os `PrintJob` correspondentes
        // ficaram pendentes no servidor, porque quem os fecharia era o
        // principal daquele momento. Ao virar principal, ele encontrava esse
        // acúmulo inteiro e mandava tudo para a impressora de uma vez — todas
        // as notas do expediente saindo de novo.
        final writes = <int>[];
        final server = await servidorComBacklog(
          criadoEm: DateTime.now()
              .toUtc()
              .subtract(const Duration(hours: 2))
              .toIso8601String(),
          writes: writes,
        );
        addTearDown(() => server.close(force: true));

        final stack = await TestPdvStack.create();
        addTearDown(stack.dispose);
        final api = ApiClient(
          baseUrl: 'http://127.0.0.1:${server.port}/api/v1',
        );
        addTearDown(api.dispose);
        api.attachLocalStore(gateway: stack.gateway);
        final agent = LocalDeviceAgent(
          api: api,
          delay: (_) async {},
          networkWriter: (target, bytes) async => writes.add(bytes.length),
        );
        addTearDown(agent.dispose);

        await agent.processPendingPrintJobsForTesting(
          token: 'tok',
          restaurantId: 'rest-1',
          takingOver: true,
        );

        expect(writes, isEmpty, reason: 'nada sai no papel sozinho');
        // Mas o cupom não some: ele fica visível na fila, esperando a decisão
        // de quem está no balcão.
        // O escopo da fila segue a sessao do token usado nas requisicoes, e
        // nao o do bind inicial do stack de teste.
        final retidos = await stack.gateway.printQueue.entries(
          scope: agent.printScope!,
        );
        expect(retidos.single.remoteJobId, 'job-antigo');
        expect(retidos.single.lastError, contains('Caixa Principal'));
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );

    test(
      'imprime normalmente o que o servidor cria depois da virada',
      () async {
        // A retenção vale só para o acúmulo herdado. Um trabalho novo é
        // responsabilidade deste terminal e tem de sair sem ninguém mandar.
        final writes = <int>[];
        final server = await servidorComBacklog(
          criadoEm: DateTime.now()
              .toUtc()
              .add(const Duration(minutes: 1))
              .toIso8601String(),
          writes: writes,
        );
        addTearDown(() => server.close(force: true));

        final stack = await TestPdvStack.create();
        addTearDown(stack.dispose);
        final api = ApiClient(
          baseUrl: 'http://127.0.0.1:${server.port}/api/v1',
        );
        addTearDown(api.dispose);
        api.attachLocalStore(gateway: stack.gateway);
        final agent = LocalDeviceAgent(
          api: api,
          delay: (_) async {},
          networkWriter: (target, bytes) async => writes.add(bytes.length),
        );
        addTearDown(agent.dispose);

        await agent.processPendingPrintJobsForTesting(
          token: 'tok',
          restaurantId: 'rest-1',
          takingOver: true,
        );

        expect(writes, hasLength(1));
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );
  });
}
