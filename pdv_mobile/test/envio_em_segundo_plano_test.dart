import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/core/sync/pending_mutation.dart';

/// A fila em memória: o teste não depende do disco do aparelho.
class _Memoria implements OfflineQueueStore {
  @override
  Future<List<PendingMutation>> load() async => [];
  @override
  Future<List<FailedMutation>> loadFailed() async => [];
  @override
  Future<void> save(List<PendingMutation> mutations) async {}
  @override
  Future<void> saveFailed(List<FailedMutation> failures) async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// O garçom não espera o servidor: a rodada vai para a fila e a tela é
/// liberada. O que não sair em 4 tentativas vai para "não enviados", onde ele
/// reenvia com um toque.
void main() {
  late List<String> enviados;
  late bool redeFora;

  BackendGateway gateway() {
    enviados = [];
    redeFora = false;
    final api = ApiClient(
      baseUrlProvider: () => 'http://loja.test/api/v1',
      // Sem nuvem: o teste é da fila, não do desvio.
      cloudFallback: CloudFallback(enabled: false),
      httpClient: MockClient((request) async {
        if (redeFora) throw http.ClientException('sem rede', request.url);
        enviados.add(request.url.path);
        return http.Response('{}', 200);
      }),
    )..configureSession(accessToken: 'a', refreshToken: 'r', terminalId: 't');
    return BackendGateway(api: api, store: _Memoria())..setAuthenticated(true);
  }

  Future<void> enfileirar(BackendGateway g, String path) => g.enqueue(
    method: 'POST',
    path: path,
    kind: 'add_item',
    summary: path,
    body: const {},
  );

  test('enfileirar devolve sem esperar a rede e sobe em ordem', () async {
    final g = gateway();
    redeFora = true;
    await enfileirar(g, '/commands/c/items/');
    await enfileirar(g, '/commands/c/send-to-kitchen/');
    expect(g.pendingCount, 2, reason: 'nada exigiu resposta do servidor');

    redeFora = false;
    await g.flushNow();
    expect(enviados, [
      '/api/v1/commands/c/items/',
      '/api/v1/commands/c/send-to-kitchen/',
    ]);
    expect(g.pendingCount, 0);
    g.dispose();
  });

  test('desiste depois de 4 tentativas e o reenvio recomeca', () async {
    final g = gateway();
    redeFora = true;
    await enfileirar(g, '/commands/c/items/');
    // O agendamento imediato do enqueue roda a 1ª tentativa.
    await Future<void>.delayed(Duration.zero);
    await Future<void>.delayed(Duration.zero);
    while (g.pendingCount > 0) {
      await g.flushNow();
    }
    expect(BackendGateway.maxTentativas, 4);
    expect(g.failed, hasLength(1));
    expect(g.failed.single.mutation.attempts, 4);
    expect(g.failed.single.reason, contains('4 tentativas'));

    redeFora = false;
    await g.retryFailed(g.failed.single.mutation.operationId);
    await g.flushNow();
    expect(g.failed, isEmpty);
    expect(enviados, ['/api/v1/commands/c/items/']);
    g.dispose();
  });
}
