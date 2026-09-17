import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/data/print_queue_service.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/storage/app_paths.dart';
import 'package:starchef_pdv_desktop/core/network/realtime_client.dart';
import 'package:starchef_pdv_desktop/features/devices/services/local_device_agent.dart';


/// JWT de mentira com `account_id`. É dele que sai o escopo do terminal, e é o
/// escopo que separa a fila de impressão de uma conta da de outra no mesmo
/// computador.
const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEiLCJ1c2VyX2lkIjoidXNyLTEifQ.'
    'assinatura-irrelevante-no-teste';

void main() {
  /// Isola o diretório de dados: a fila da impressora é um arquivo, e dois
  /// testes no mesmo arquivo veriam os cupons um do outro.
  Future<Directory> isolatedDataDirectory() async {
    final directory = await Directory.systemTemp.createTemp('starchef-agent');
    AppPaths.overrideDataDirectory(directory);
    addTearDown(() async {
      AppPaths.overrideDataDirectory(null);
      try {
        await directory.delete(recursive: true);
      } on FileSystemException {
        // No Windows o arquivo pode continuar preso por instantes.
      }
    });
    return directory;
  }

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

    test('a marca do documento impresso sobrevive em disco', () async {
      await isolatedDataDirectory();
      final queue = PrintQueueService();
      const scope = 'servidor|acc-1';
      const key = 'danfe:CHAVE-1';

      expect(
        await queue.wasDocumentPrinted(scope: scope, dedupeKey: key),
        isFalse,
      );

      await queue.markDocumentPrinted(scope: scope, dedupeKey: key);

      expect(
        await queue.wasDocumentPrinted(scope: scope, dedupeKey: key),
        isTrue,
      );
      // Marcar de novo não é erro: os dois caminhos (fila e impressão manual)
      // escrevem a mesma chave.
      await queue.markDocumentPrinted(scope: scope, dedupeKey: key);
      expect(
        await queue.wasDocumentPrinted(scope: scope, dedupeKey: 'danfe:OUTRA'),
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
    test(
      'uma impressora fora do ar não segura o cupom das outras',
      () async {
        // O sintoma era exatamente este: o cupom do bar travado numa térmica
        // de rede sem resposta, e a comanda da cozinha — enfileirada depois,
        // numa impressora que estava funcionando — nunca saindo, sem erro
        // nenhum na tela. A drenagem parava no primeiro que falhava.
        await isolatedDataDirectory();
        final api = ApiClient(
          baseUrl: 'http://starchef.test/api/v1',
          client: MockClient((_) async => http.Response('{}', 200)),
        );
        addTearDown(api.dispose);
        // Uma requisição autenticada é o que dá escopo ao terminal.
        await api.get('/health/', accessToken: _token);
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

        final scope = agent.printScope!;
        final queue = agent.printQueue;
        await queue.enqueue(
          scope: scope,
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
          scope: scope,
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
        final resumo = await queue.summary(scope: scope);
        // O cupom do bar continua na fila para a próxima tentativa; o da
        // cozinha já saiu no papel.
        expect(resumo.pending, 1);
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );

    test('a fila é do terminal, não do operador do turno', () async {
      // Um cupom que ficou esperando papel no turno da manhã precisa sair
      // quando o operador da tarde entrar. Escopo por usuário deixaria esse
      // cupom órfão no arquivo, invisível para a fila seguinte.
      await isolatedDataDirectory();
      const manha =
          'eyJhbGciOiJIUzI1NiJ9.'
          'eyJhY2NvdW50X2lkIjoiYWNjLTEiLCJ1c2VyX2lkIjoibWFuaGEifQ.'
          'assinatura';
      const tarde =
          'eyJhbGciOiJIUzI1NiJ9.'
          'eyJhY2NvdW50X2lkIjoiYWNjLTEiLCJ1c2VyX2lkIjoidGFyZGUifQ.'
          'assinatura';
      final api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient((_) async => http.Response('{}', 200)),
      );
      addTearDown(api.dispose);

      await api.get('/health/', accessToken: manha);
      final escopoManha = api.terminalScope;
      await api.get('/health/', accessToken: tarde);

      expect(api.terminalScope, escopoManha);
      // E o operador mudou de fato: o que é da sessão continua separado.
      expect(api.sessionScope, isNot('acc-1:manha'));
    });
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
              // O agente pede os tres estados numa consulta so (`status__in`).
              final estados =
                  request.uri.queryParameters['status__in']?.split(',') ??
                  const <String>[];
              response.write(
                jsonEncode({
                  'results': estados.contains('pending')
                      ? [
                          {
                            'id': 'job-1',
                            'status': 'pending',
                            'job_type': 'weigh_ticket',
                            'printer': 'printer-1',
                            'created_at': DateTime.now()
                                .toUtc()
                                .toIso8601String(),
                            'payload': {'text_content': 'NOTA DE PESAGEM'},
                          },
                        ]
                      : const [],
                }),
              );
            case '/api/v1/print-jobs/job-1/claim/':
              response.write(jsonEncode({'id': 'job-1', 'status': 'claimed'}));
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

        await isolatedDataDirectory();
        final api = ApiClient(
          baseUrl: 'http://127.0.0.1:${server.port}/api/v1',
        );
        addTearDown(api.dispose);
        final agent = LocalDeviceAgent(
          api: api,
          networkWriter: (target, bytes) async => writes++,
        );

        await agent.processPendingPrintJobsForTesting(
          token: _token,
          restaurantId: 'rest-1',
        );
        expect(writes, 1, reason: 'primeiro ciclo imprime fisicamente');
        expect(markPrintedAttempts, 1);

        // mark-printed falhou no ciclo anterior: o job continua "pending" no
        // servidor de mentira e volta a aparecer aqui — sem a correção, isto
        // reimprimiria o mesmo cupom.
        await agent.processPendingPrintJobsForTesting(
          token: _token,
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

  group('LocalDeviceAgent reserva o cupom antes de imprimir', () {
    /// Servidor de mentira com um cupom pendente e uma reserva configurável.
    Future<HttpServer> servidorComCupom({
      required int statusDaReserva,
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
            // O agente pede os tres estados numa consulta so (`status__in`),
            // e nao um por vez — ver `agente_carga_no_servidor_test.dart`.
            final estados =
                request.uri.queryParameters['status__in']?.split(',') ??
                const <String>[];
            response.write(
              jsonEncode({
                'results': estados.contains('pending')
                    ? [
                        {
                          'id': 'job-disputado',
                          'status': 'pending',
                          'job_type': 'weigh_ticket',
                          'printer': 'printer-1',
                          'created_at': DateTime.now()
                              .toUtc()
                              .toIso8601String(),
                          'payload': {'text_content': 'NOTA DE PESAGEM'},
                        },
                      ]
                    : const [],
              }),
            );
          case '/api/v1/print-jobs/job-disputado/claim/':
            response.statusCode = statusDaReserva;
            response.write(
              jsonEncode(
                statusDaReserva == HttpStatus.ok
                    ? {'id': 'job-disputado', 'status': 'claimed'}
                    : {'detail': 'Ja assumido por outro terminal.'},
              ),
            );
          case '/api/v1/print-jobs/job-disputado/mark-printed/':
            response.write(jsonEncode({'ok': true}));
          default:
            response.statusCode = HttpStatus.notFound;
        }
        await response.close();
      });
      return server;
    }

    test(
      'perder a reserva para outro terminal não imprime nada',
      () async {
        // A fila é da UNIDADE: dois PDVs enxergam o mesmo cupom, e a
        // impressora de rede é alcançável dos dois. Sem a reserva, a comanda
        // sairia duas vezes na cozinha.
        await isolatedDataDirectory();
        final writes = <int>[];
        final server = await servidorComCupom(
          statusDaReserva: HttpStatus.conflict,
          writes: writes,
        );
        addTearDown(() => server.close(force: true));

        final api = ApiClient(
          baseUrl: 'http://127.0.0.1:${server.port}/api/v1',
        );
        addTearDown(api.dispose);
        final agent = LocalDeviceAgent(
          api: api,
          delay: (_) async {},
          networkWriter: (target, bytes) async => writes.add(bytes.length),
        );
        addTearDown(agent.dispose);

        await agent.processPendingPrintJobsForTesting(
          token: _token,
          restaurantId: 'rest-1',
        );

        expect(writes, isEmpty, reason: 'o cupom é do outro terminal');
        // E não fica um fantasma na fila local esperando alguém decidir.
        expect(
          await agent.printQueue.entries(scope: agent.printScope!),
          isEmpty,
        );
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );

    test(
      'ganhar a reserva imprime normalmente',
      () async {
        await isolatedDataDirectory();
        final writes = <int>[];
        final server = await servidorComCupom(
          statusDaReserva: HttpStatus.ok,
          writes: writes,
        );
        addTearDown(() => server.close(force: true));

        final api = ApiClient(
          baseUrl: 'http://127.0.0.1:${server.port}/api/v1',
        );
        addTearDown(api.dispose);
        final agent = LocalDeviceAgent(
          api: api,
          delay: (_) async {},
          networkWriter: (target, bytes) async => writes.add(bytes.length),
        );
        addTearDown(agent.dispose);

        await agent.processPendingPrintJobsForTesting(
          token: _token,
          restaurantId: 'rest-1',
        );

        expect(writes, hasLength(1));
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );
  });
}
