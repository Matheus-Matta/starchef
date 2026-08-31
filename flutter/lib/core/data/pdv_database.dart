import 'dart:io';

import 'package:sqlite_async/sqlite_async.dart';

import '../storage/app_paths.dart';

/// Banco operacional do Caixa Principal.
///
/// É a **fonte de verdade local de toda a operação** (§1). Antes existiam dois
/// arquivos com propósitos parecidos — `offline_data.sqlite` guardava respostas
/// HTTP e a fila; `local_orders.sqlite` guardava pedidos já com as alterações
/// offline. Nenhum dos dois guardava *entidades* de forma uniforme, então
/// produto, mesa, impressora, caixa e configuração fiscal só existiam
/// localmente enquanto uma resposta HTTP correspondente estivesse em cache.
///
/// Aqui há uma tabela única de entidades: qualquer recurso da API é gravado
/// com versão, origem (LOCAL/REMOTE), estado de sincronização e exclusão
/// lógica. Isso é o que permite ler, escrever e paginar sem rede.
///
/// `sqlite_async` mantém o I/O fora da isolate de UI, usa WAL por padrão
/// (§20) e coordena vários engines sobre o mesmo arquivo — o PDV, a janela da
/// Balança Rápida e o servidor local compartilham este banco com segurança.
class PdvDatabase {
  PdvDatabase({File? file}) : _file = file ?? _defaultFile() {
    _database = SqliteDatabase(path: _file.path);
    _ready = _initialize();
  }

  static const schemaVersion = 6;

  final File _file;
  late final SqliteDatabase _database;
  late final Future<void> _ready;
  bool _closed = false;

  static File _defaultFile() => AppPaths.dataFile('pdv_operational.sqlite');

  /// Conclui migrations e integridade antes do primeiro uso (§24, passos 2-3).
  Future<void> get ready => _ready;

  SqliteDatabase get raw => _database;

  String get path => _file.path;

  Future<void> _initialize() async {
    await _file.parent.create(recursive: true);
    final migrations = SqliteMigrations()
      ..createDatabase = SqliteMigration(schemaVersion, _createSchema)
      ..add(SqliteMigration(1, _createSchema))
      ..add(SqliteMigration(2, _createPrintQueue))
      ..add(SqliteMigration(3, _createSecureValues))
      ..add(SqliteMigration(4, _createQueueOrigin))
      ..add(SqliteMigration(5, _createCodeIndex))
      ..add(SqliteMigration(6, _createFiscalSnapshot));
    await migrations.migrate(_database);
    // WAL permite ler enquanto se grava (§20). `sqlite_async` já o ativa por
    // padrão; o comando explícito documenta a dependência e protege contra uma
    // mudança de padrão da biblioteca.
    await _database.execute('PRAGMA journal_mode = WAL');
    // O PDV e a janela da Balança Rápida são dois PROCESSOS sobre o mesmo
    // arquivo. Sem espera, uma gravação simultânea devolve `SQLITE_BUSY` na
    // hora e a venda falharia por um bloqueio de milissegundos — em Windows e
    // Linux igualmente. Cinco segundos é muito mais do que qualquer transação
    // daqui leva, e muito menos do que a paciência de quem está no balcão.
    await _database.execute('PRAGMA busy_timeout = 5000');
  }

  /// Confere se o arquivo não está corrompido antes de operar sobre ele.
  ///
  /// Um banco corrompido que só falha na primeira venda é pior do que um erro
  /// na abertura: o operador já teria clientes na fila.
  Future<bool> verifyIntegrity() async {
    await _ready;
    final row = await _database.getOptional('PRAGMA quick_check');
    if (row == null) return false;
    return '${row.values.first}'.toLowerCase() == 'ok';
  }

  Future<T> write<T>(Future<T> Function(SqliteWriteContext tx) action) async {
    await _ready;
    return _database.writeTransaction(action);
  }

  Future<List<Map<String, Object?>>> query(
    String sql, [
    List<Object?> parameters = const [],
  ]) async {
    await _ready;
    return _database.getAll(sql, parameters);
  }

  Future<Map<String, Object?>?> querySingle(
    String sql, [
    List<Object?> parameters = const [],
  ]) async {
    await _ready;
    return _database.getOptional(sql, parameters);
  }

  Future<void> execute(String sql, [List<Object?> parameters = const []]) async {
    await _ready;
    await _database.execute(sql, parameters);
  }

  /// Fila de impressão local (§17).
  ///
  /// A fila de trabalhos sempre viveu no backend: o agente perguntava
  /// `/print-jobs/` e imprimia. Com a internet fora, não havia o que
  /// perguntar — e nada saía no papel. Aqui a fila é do terminal: qualquer
  /// cupom, tenha sido montado aqui ou vindo do servidor, espera nela até a
  /// impressora aceitar.
  static Future<void> _createPrintQueue(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS print_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL UNIQUE,
        scope TEXT NOT NULL,
        remote_job_id TEXT,
        printer_id TEXT NOT NULL,
        printer_json TEXT NOT NULL,
        job_type TEXT NOT NULL,
        content TEXT NOT NULL,
        barcode TEXT,
        qr TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        next_retry_at TEXT,
        last_error TEXT,
        printed_at TEXT,
        lease_owner TEXT,
        lease_until TEXT
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS print_queue_fifo_idx
      ON print_queue(scope, status, next_retry_at, id)
    ''');
    // O id do trabalho no servidor é único: é ele que impede o mesmo cupom de
    // entrar duas vezes quando o `mark-printed` não confirma e o job volta a
    // aparecer na consulta seguinte.
    await tx.execute('''
      CREATE UNIQUE INDEX IF NOT EXISTS print_queue_remote_idx
      ON print_queue(scope, remote_job_id)
      WHERE remote_job_id IS NOT NULL
    ''');
  }

  /// Credenciais que precisam sobreviver a fechar o PDV (§30).
  ///
  /// O cofre do sistema é a primeira escolha, mas em Ubuntu ele falta com
  /// frequência: autostart sem sessão gráfica, keyring bloqueado, pacote sem
  /// Secret Service. A cópia em arquivo cobria parte disso e ainda dependia de
  /// `chmod`. Este banco é o mesmo que guarda caixa e pedidos e já provou
  /// sobreviver — o login passa a morar junto.
  ///
  /// O verificador de senha é PBKDF2: guardá-lo em repouso é seguro, é para
  /// isso que ele existe. Os tokens de sessão são cifrados quando há cofre; sem
  /// cofre ficam em texto, exatamente como já ficavam na cópia em arquivo.
  static Future<void> _createSecureValues(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS secure_values (
        value_key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    ''');
  }

  /// Credenciais de origem na fila de saída (§8).
  ///
  /// A fila do Caixa Principal deixou de ser só dele: ela entrega também o que
  /// os caixas secundários originaram, e cada operação precisa subir com as
  /// credenciais de QUEM a originou. Sem isso, uma venda do PDV 2 chegava ao
  /// backend no nome do PDV 1 — e a sessão de caixa, que pertence ao par
  /// (operador, terminal), ficava com o dono errado.
  static Future<void> _createQueueOrigin(SqliteWriteContext tx) async {
    await tx.execute('ALTER TABLE sync_queue ADD COLUMN origin_json TEXT');
  }

  /// Índice de códigos lidos por leitor (§scanner).
  ///
  /// Achar o produto de um código de barras varrendo o catálogo significaria
  /// ler e decifrar milhares de payloads a cada bipe — no balcão, com o
  /// cliente esperando. Uma tabela pequena, indexada pelo código, transforma
  /// isso em uma consulta direta.
  /// Retrato fiscal e resposta do servidor na fila de notas.
  ///
  /// `snapshot` guarda a tributação resolvida no instante do pagamento — sem
  /// ele, emitir sem o servidor é impossível, porque a fila só tinha pedido e
  /// CPF. `response` existe porque a resposta era gravada por cima de
  /// `payload`, apagando o que havia sido enviado justamente quando alguém
  /// precisava comparar os dois.
  static Future<void> _createFiscalSnapshot(SqliteWriteContext tx) async {
    for (final column in ['snapshot TEXT', 'response TEXT', 'invoice_id TEXT']) {
      try {
        await tx.execute('ALTER TABLE fiscal_queue ADD COLUMN $column');
      } on Object {
        // Coluna já existe (banco criado pelo schema novo): nada a fazer.
      }
    }
  }

  static Future<void> _createCodeIndex(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS entity_codes (
        scope TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        field TEXT NOT NULL,
        code TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        PRIMARY KEY (scope, entity_type, field, code, entity_id)
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS entity_codes_lookup_idx
      ON entity_codes(scope, entity_type, code)
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS entity_codes_entity_idx
      ON entity_codes(scope, entity_type, entity_id)
    ''');
  }

  static Future<void> _createSchema(SqliteWriteContext tx) async {
    // ---------------------------------------------------------------------
    // Entidades: uma linha por recurso do restaurante, qualquer que seja o
    // tipo. Os campos de controle (§21) são os mesmos para todos, e é isso
    // que permite um único serviço de sincronização atender pedido, produto,
    // impressora e configuração fiscal sem repetir regra por tela.
    // ---------------------------------------------------------------------
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS entities (
        scope TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        parent_id TEXT,
        restaurant_id TEXT,
        status TEXT,
        payload TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        server_version TEXT,
        source TEXT NOT NULL DEFAULT 'LOCAL',
        sync_status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        sort_key TEXT NOT NULL,
        deleted_at TEXT,
        PRIMARY KEY (scope, entity_type, entity_id)
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS entities_list_idx
      ON entities(scope, entity_type, deleted_at, sort_key DESC)
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS entities_parent_idx
      ON entities(scope, entity_type, parent_id)
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS entities_restaurant_idx
      ON entities(scope, entity_type, restaurant_id, status)
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS entities_dirty_idx
      ON entities(scope, sync_status)
    ''');

    // ---------------------------------------------------------------------
    // Fila de sincronização (§5). Gravada na MESMA transação da entidade, de
    // modo que nunca exista um pedido salvo sem a operação correspondente.
    // O `id` autoincremental é a ordem FIFO (§6): duas operações criadas no
    // mesmo milissegundo continuam com ordem determinística.
    // ---------------------------------------------------------------------
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_id TEXT NOT NULL UNIQUE,
        scope TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        query_json TEXT,
        payload TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        next_retry_at TEXT,
        last_error TEXT,
        lease_owner TEXT,
        lease_until TEXT,
        -- Credenciais de quem originou a operação, quando não foi este
        -- terminal. Ver `_createQueueOrigin`.
        origin_json TEXT
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS sync_queue_fifo_idx
      ON sync_queue(scope, status, next_retry_at, id)
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS sync_queue_entity_idx
      ON sync_queue(scope, entity_type, entity_id)
    ''');

    await _createCodeIndex(tx);

    // Marca de tempo por tipo, para o delta sync (§14) não rebaixar a base
    // inteira a cada reconexão.
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS sync_state (
        scope TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        last_sync_at TEXT,
        cursor TEXT,
        last_error TEXT,
        PRIMARY KEY (scope, entity_type)
      )
    ''');

    // Fila fiscal própria (§16): a venda conclui local e o documento segue
    // sua vida separada, com prioridade e diagnóstico independentes.
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS fiscal_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id TEXT NOT NULL UNIQUE,
        scope TEXT NOT NULL,
        order_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        snapshot TEXT,
        response TEXT,
        invoice_id TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        next_retry_at TEXT,
        last_error TEXT,
        protocol TEXT
      )
    ''');
    await tx.execute('''
      CREATE INDEX IF NOT EXISTS fiscal_queue_status_idx
      ON fiscal_queue(scope, status, next_retry_at, id)
    ''');

    await _createPrintQueue(tx);
    await _createSecureValues(tx);

    // Tradução ID local -> ID do servidor, usada para reescrever referências
    // pendentes assim que a criação sobe.
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS id_map (
        scope TEXT NOT NULL,
        local_id TEXT NOT NULL,
        remote_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (scope, local_id)
      )
    ''');
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    await _ready;
    await _database.close();
  }
}
