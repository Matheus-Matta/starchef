import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';

import 'pdv_test_support.dart';

/// O Caixa Secundário não tem WebSocket: só o `pullAll` periódico o avisa do
/// que os outros terminais fizeram. A cadência dele tem de ser curta — e tem
/// de mudar em tempo de execução, porque o papel muda em Configurações sem
/// reiniciar o app.
void main() {
  late TestPdvStack stack;
  late FakeSyncTransport transport;
  late SyncService sync;

  setUp(() async {
    stack = await TestPdvStack.create();
    transport = FakeSyncTransport();
    sync = SyncService(
      gateway: stack.gateway,
      transport: transport,
      pullInterval: const Duration(hours: 1),
    );
  });

  tearDown(() async {
    await sync.dispose();
    await stack.dispose();
  });

  test('a cadência de pull do secundário é bem menor que a padrão', () {
    expect(
      SyncService.secondaryPullInterval,
      lessThanOrEqualTo(const Duration(seconds: 30)),
    );
  });

  test('usePullInterval reprograma o temporizador com o serviço já rodando', () async {
    sync.start();
    // Com uma hora de intervalo, nada aconteceria neste teste.
    transport.requests.clear();

    sync.usePullInterval(const Duration(milliseconds: 60));
    await Future<void>.delayed(const Duration(milliseconds: 250));
    sync.stop();

    final leituras = transport.requests.where((r) => r.method == 'GET').length;
    expect(
      leituras,
      greaterThan(0),
      reason: 'o pull passou a rodar na cadência nova sem reiniciar o serviço',
    );
    expect(sync.pullInterval, const Duration(milliseconds: 60));
  });
}
