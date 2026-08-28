import '../logging/app_logger.dart';
import '../network/api_client.dart';
import '../storage/durable_secure_store.dart';
import 'fiscal_queue_service.dart';
import 'offline_first_gateway.dart';
import 'payload_cipher.dart';
import 'pdv_database.dart';
import 'sync_queue_service.dart';
import 'sync_service.dart';

/// Montagem e partida do núcleo operacional local (§24).
///
/// A ordem importa e é exatamente a pedida na arquitetura:
///
/// 1. abrir o SQLite;
/// 2. executar as migrations;
/// 3. verificar a integridade;
/// 4. montar a fila de saída, a fila fiscal e a de impressão;
/// 5. ligar o gateway ao cliente HTTP.
///
/// A sincronização **não** começa aqui: ela precisa de um escopo, e escopo só
/// existe depois do login. Quem a inicia é o `ApiClient`, ao reconhecer a
/// sessão na primeira requisição autenticada.
///
/// Nada disso bloqueia a interface: se existir um SQLite válido, o PDV abre e
/// opera. Sincronização, WebSocket e servidor local sobem depois, cada um no
/// seu tempo.
class PdvRuntime {
  PdvRuntime._({
    required this.database,
    required this.queue,
    required this.fiscalQueue,
    required this.gateway,
    required this.sync,
  });

  final PdvDatabase database;
  final SyncQueueService queue;
  final FiscalQueueService fiscalQueue;
  final OfflineFirstGateway gateway;
  final SyncService sync;

  bool _closed = false;

  /// Prepara o núcleo e o conecta ao [api].
  ///
  /// [cipherStore] guarda a chave que protege os payloads sigilosos (§15).
  /// Passar `null` desliga a proteção: só os testes fazem isso, porque em
  /// produção as duas janelas compartilham o mesmo banco e uma delas gravando
  /// em texto deixaria a outra sem conseguir ler.
  static Future<PdvRuntime> start({
    required ApiClient api,
    PdvDatabase? database,
    SecureValueStore? cipherStore,
    Duration pullInterval = const Duration(minutes: 5),
  }) async {
    final db = database ?? PdvDatabase();
    await db.ready;

    final healthy = await db.verifyIntegrity();
    if (!healthy) {
      // Não é motivo para impedir a abertura: o PDV ainda opera, e uma venda
      // perdida por banco corrompido tem de aparecer no log em vez de virar
      // um erro silencioso no meio do turno.
      AppLogger.instance.error(
        'sqlite_integridade_falhou',
        data: {'arquivo': db.path},
      );
    }

    final queue = SyncQueueService(database: db);
    final fiscalQueue = FiscalQueueService(database: db);
    final gateway = OfflineFirstGateway(
      database: db,
      queue: queue,
      fiscalQueue: fiscalQueue,
      cipher: cipherStore == null
          ? PayloadCipher.disabled()
          : PayloadCipher(store: cipherStore),
    );
    final sync = SyncService(
      gateway: gateway,
      transport: api.syncTransport,
      pullInterval: pullInterval,
    );

    api.attachLocalStore(gateway: gateway, syncService: sync);
    AppLogger.instance.info(
      'pdv_runtime_pronto',
      data: {'banco': db.path, 'integridade': healthy},
    );
    return PdvRuntime._(
      database: db,
      queue: queue,
      fiscalQueue: fiscalQueue,
      gateway: gateway,
      sync: sync,
    );
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    await sync.dispose();
    await database.close();
  }
}
