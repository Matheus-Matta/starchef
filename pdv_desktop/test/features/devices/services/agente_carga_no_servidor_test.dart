import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/data/print_queue_service.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/storage/app_paths.dart';
import 'package:starchef_pdv_desktop/features/devices/services/local_device_agent.dart';

const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEiLCJ1c2VyX2lkIjoidXNyLTEifQ.'
    'assinatura-irrelevante-no-teste';

/// Quanto o agente pesa no servidor, e o que ele decide NÃO imprimir.
///
/// O PDV é um terminal de loja: ele fica horas aberto, e cada requisição
/// periódica se multiplica por terminal e por loja. O WebSocket já avisa de
/// cada `PrintJob` no instante em que nasce — a consulta periódica é só rede
/// de segurança.
void main() {
  late Directory diretorio;
  late HttpServer servidor;
  late List<Uri> consultas;
  late List<Map<String, dynamic>> trabalhos;
  late List<int> escritas;

  Map<String, dynamic> trabalho({
    required String id,
    required String status,
    String? printerId,
    Duration idade = Duration.zero,
  }) => {
    'id': id,
    'status': status,
    'job_type': 'kitchen_ticket',
    'printer': printerId,
    'created_at': DateTime.now().toUtc().subtract(idade).toIso8601String(),
    'payload': {'text_content': 'COMANDA $id'},
  };

  setUp(() async {
    diretorio = await Directory.systemTemp.createTemp('starchef-carga');
    AppPaths.overrideDataDirectory(diretorio);
    consultas = [];
    trabalhos = [];
    escritas = [];

    servidor = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    servidor.listen((request) async {
      consultas.add(request.uri);
      final response = request.response
        ..headers.contentType = ContentType.json;
      if (request.uri.path == '/api/v1/printers/') {
        response.write(
          jsonEncode({
            'results': [
              {
                'id': 'printer-1',
                'name': 'Cozinha',
                'connection_type': 'network',
                'host': '192.0.2.10',
                'port': 9100,
                'driver_type': 'escpos',
                'auto_print': true,
              },
            ],
          }),
        );
      } else if (request.uri.path == '/api/v1/print-jobs/') {
        response.write(jsonEncode({'results': trabalhos}));
      } else if (request.uri.path.endsWith('/claim/')) {
        response.write(jsonEncode({'status': 'claimed'}));
      } else if (request.uri.path.endsWith('/mark-printed/')) {
        response.write(jsonEncode({'ok': true}));
      } else {
        response.statusCode = HttpStatus.notFound;
        response.write(jsonEncode({'detail': 'nao encontrado'}));
      }
      await response.close();
    });
  });

  tearDown(() async {
    await servidor.close(force: true);
    AppPaths.overrideDataDirectory(null);
    try {
      await diretorio.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  LocalDeviceAgent montarAgente() {
    final api = ApiClient(baseUrl: 'http://127.0.0.1:${servidor.port}/api/v1');
    addTearDown(api.dispose);
    final agente = LocalDeviceAgent(
      api: api,
      delay: (_) async {},
      networkWriter: (_, bytes) async => escritas.add(bytes.length),
    );
    addTearDown(agente.dispose);
    return agente;
  }

  test('a lista de trabalhos sai numa requisição, não numa por status', () async {
    final agente = montarAgente();

    await agente.processPendingPrintJobsForTesting(
      token: _token,
      restaurantId: 'rest-1',
    );

    final deTrabalhos = consultas
        .where((uri) => uri.path == '/api/v1/print-jobs/')
        .toList();
    expect(deTrabalhos, hasLength(1));
    // Os três estados de uma vez — era uma chamada para cada.
    expect(
      deTrabalhos.single.queryParameters['status__in'],
      'scheduled,pending,rendered',
    );
    // E do mais novo para o mais velho: com acumulado, a primeira página
    // precisa ser a das comandas recentes.
    expect(deTrabalhos.single.queryParameters['ordering'], '-created_at');
  });

  test('cupom velho não vai para o papel', () async {
    // O caso real: uma loja com dezenas de trabalhos parados há semanas. Sem
    // este corte, o primeiro terminal a subir despeja tudo na cozinha.
    trabalhos = [
      trabalho(
        id: 'antigo',
        status: 'rendered',
        printerId: 'printer-1',
        idade: PrintQueueService.expiresAfter + const Duration(hours: 1),
      ),
      trabalho(
        id: 'novo',
        status: 'rendered',
        printerId: 'printer-1',
        idade: const Duration(minutes: 3),
      ),
    ];
    final agente = montarAgente();

    await agente.processPendingPrintJobsForTesting(
      token: _token,
      restaurantId: 'rest-1',
    );

    // Só o recente foi reservado e impresso.
    final reservas = consultas
        .where((uri) => uri.path.endsWith('/claim/'))
        .map((uri) => uri.path)
        .toList();
    expect(reservas, hasLength(1));
    expect(reservas.single, contains('novo'));
    expect(escritas, hasLength(1));
  });

  test('cupom sem impressora avisa uma vez, não a cada ciclo', () async {
    // A retaguarda web cria trabalho sem equipamento (ela imprime pelo
    // navegador). Ele nunca sai daqui, e reclamar a cada dois minutos afoga o
    // log justamente quando alguém precisa lê-lo.
    trabalhos = [trabalho(id: 'sem-impressora', status: 'rendered')];
    final agente = montarAgente();

    await agente.processPendingPrintJobsForTesting(
      token: _token,
      restaurantId: 'rest-1',
    );
    await agente.processPendingPrintJobsForTesting(
      token: _token,
      restaurantId: 'rest-1',
    );

    // Duas consultas aconteceram, mas nada foi reservado nem impresso.
    expect(consultas.where((uri) => uri.path.endsWith('/claim/')), isEmpty);
    expect(escritas, isEmpty);
  });
}
