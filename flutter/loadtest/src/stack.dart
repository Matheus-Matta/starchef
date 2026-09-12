/// O nucleo do PDV montado de verdade, so que apontado para um diretorio
/// temporario e um transporte controlado.
///
/// Nada aqui e duplo: o SQLite e o mesmo `PdvDatabase` de producao, a fila e o
/// mesmo `SyncQueueService`, o roteamento e o mesmo `OfflineFirstGateway`.
/// Trocar isso por um dobro provaria o dobro, nao o produto.
library;

import 'dart:io';

import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/print_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_exception.dart';
import 'package:starchef_pdv/core/network/relay_origin.dart';

/// Transporte que o teste controla: nenhuma chamada sai da maquina.
///
/// Ele imita o backend o suficiente para a fila fazer sentido — devolve id
/// definitivo na criacao, respeita a chave de idempotencia e sabe ficar fora
/// do ar, lento ou instavel sob comando.
class TransporteDeCarga implements SyncTransport {
  TransporteDeCarga();

  bool online = true;

  /// Atraso artificial por requisicao — o "servidor lento" do mundo real.
  Duration latencia = Duration.zero;

  /// Fracao das entregas que falha temporariamente (5xx/timeout).
  double falhaTemporaria = 0;

  /// Fracao das entregas que e recusada por regra de negocio (4xx).
  double recusaDefinitiva = 0;

  /// Fracao das respostas que chega corrompida — HTML de um proxy, JSON
  /// truncado, corpo que nao e o esperado. Nao e hipotese: um 502 de proxy
  /// reverso devolve pagina HTML, e o `jsonDecode` estoura FormatException.
  double respostaCorrompida = 0;

  int entregas = 0;
  int repeticoesIdempotentes = 0;
  final Map<String, Map<String, dynamic>> _recibos = {};
  final List<String> rotas = [];
  int _semente = 7;

  double _sorteio() {
    _semente = (_semente * 1103515245 + 12345) & 0x7FFFFFFF;
    return (_semente % 10000) / 10000.0;
  }

  @override
  Future<bool> ping() async => online;

  @override
  Future<Map<String, dynamic>> send(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Map<String, dynamic>? body,
    String? idempotencyKey,
    RelayOrigin? origin,
    void Function(RelayOrigin renewed)? onOriginRenewed,
  }) async {
    rotas.add('$method $path');
    if (latencia > Duration.zero) {
      await Future<void>.delayed(latencia);
    }
    if (!online) {
      throw const TransientSyncFailure('Sem conexao com o servidor.');
    }
    final chave = idempotencyKey ?? '';
    final recibo = _recibos[chave];
    if (chave.isNotEmpty && recibo != null) {
      // A mesma chave devolve a MESMA resposta: e o contrato do
      // IdempotencyMiddleware do backend, e o que impede venda duplicada.
      repeticoesIdempotentes++;
      return recibo;
    }
    final sorteio = _sorteio();
    if (sorteio < falhaTemporaria) {
      throw const TransientSyncFailure('Servidor instavel (simulado).');
    }
    if (sorteio < falhaTemporaria + recusaDefinitiva) {
      throw const ApiException(
        'Recusado pela regra de negocio (simulado).',
        statusCode: 400,
      );
    }
    if (sorteio < falhaTemporaria + recusaDefinitiva + respostaCorrompida) {
      // O que um proxy reverso devolve quando o backend cai: HTML, nao JSON.
      throw const FormatException('Unexpected character (at character 1)');
    }
    entregas++;
    final resposta = _responder(method, path, body);
    if (chave.isNotEmpty) _recibos[chave] = resposta;
    return resposta;
  }

  Map<String, dynamic> _responder(
    String method,
    String path,
    Map<String, dynamic>? body,
  ) {
    // Criacao devolve id definitivo: e o que dispara a troca do `offline-...`
    // por ele no banco, nos pais e no resto da fila.
    final identificador = 'srv-${entregas.toString().padLeft(8, '0')}';
    return <String, dynamic>{
      'id': identificador,
      ...?body,
      'status': body?['status'] ?? 'open',
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    };
  }
}

/// Um terminal completo: banco, filas, gateway e sincronizacao.
class PilhaDeCarga {
  PilhaDeCarga._({
    required this.nome,
    required this.diretorio,
    required this.banco,
    required this.fila,
    required this.filaFiscal,
    required this.filaImpressao,
    required this.gateway,
    required this.transporte,
    required this.sync,
  });

  static const escopo = 'carga.local|conta-carga:operador-carga';
  static const restauranteId = 'rest-carga';

  final String nome;
  final Directory diretorio;
  final PdvDatabase banco;
  final SyncQueueService fila;
  final FiscalQueueService filaFiscal;
  final PrintQueueService filaImpressao;
  final OfflineFirstGateway gateway;
  final TransporteDeCarga transporte;
  final SyncService sync;

  static Future<PilhaDeCarga> criar({String nome = 'principal'}) async {
    final diretorio = await Directory.systemTemp.createTemp('starchef-carga-');
    final banco = PdvDatabase(
      file: File('${diretorio.path}${Platform.pathSeparator}pdv.sqlite'),
    );
    await banco.ready;
    final fila = SyncQueueService(database: banco);
    final filaFiscal = FiscalQueueService(database: banco);
    final filaImpressao = PrintQueueService(database: banco, leaseOwner: nome);
    final gateway = OfflineFirstGateway(
      database: banco,
      queue: fila,
      fiscalQueue: filaFiscal,
    )..bindSession(scope: escopo, restaurantId: restauranteId);
    final transporte = TransporteDeCarga();
    // O SyncService pega fila e escopo do proprio gateway; so o transporte
    // e injetado — e e exatamente ele que este teste controla.
    final sync = SyncService(gateway: gateway, transport: transporte);
    return PilhaDeCarga._(
      nome: nome,
      diretorio: diretorio,
      banco: banco,
      fila: fila,
      filaFiscal: filaFiscal,
      filaImpressao: filaImpressao,
      gateway: gateway,
      transporte: transporte,
      sync: sync,
    );
  }

  Future<void> descartar() async {
    await sync.dispose();
    await banco.close();
    try {
      if (await diretorio.exists()) await diretorio.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  }
}
