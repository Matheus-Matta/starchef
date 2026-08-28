import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/payload_cipher.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sqlite_secure_value_store.dart';
import 'package:starchef_pdv/core/storage/durable_secure_store.dart';
import 'package:starchef_pdv/features/auth/data/offline_login_store.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';

/// **O login precisa sobreviver a fechar o PDV.**
///
/// Em Ubuntu o cofre do sistema falta com frequência — autostart sem sessão
/// gráfica, keyring bloqueado, pacote sem Secret Service — e a cópia em
/// arquivo ainda dependia de `chmod` funcionar no volume do `$HOME`. Quando os
/// dois falhavam, o operador perdia a sessão ao fechar o aplicativo e não
/// conseguia entrar no dia seguinte, justamente quando a internet estava fora.
///
/// O banco operacional é a terceira camada: o mesmo arquivo que já guarda
/// pedidos, caixa e fila de impressão.
void main() {
  late Directory directory;
  late PdvDatabase database;

  final session = AuthSession(
    accessToken: 'token-de-acesso',
    refreshToken: 'token-de-renovacao',
    user: const AuthUser(
      id: 'user-1',
      username: 'ana',
      name: 'Ana',
      profileType: 'cashier',
      accountId: 'conta-1',
      restaurantId: 'rest-1',
    ),
  );

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-credenciais');
    database = PdvDatabase(
      file: File('${directory.path}${Platform.pathSeparator}pdv.sqlite'),
    );
    await database.ready;
  });

  tearDown(() async {
    await database.close();
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  SqliteSecureValueStore sqliteStore() =>
      SqliteSecureValueStore(database: database);

  test('a credencial sobrevive a fechar e abrir o aplicativo', () async {
    await sqliteStore().write('starchef_access_token', 'token-de-acesso');

    // Uma instância nova, como acontece no próximo boot.
    expect(
      await sqliteStore().read('starchef_access_token'),
      'token-de-acesso',
    );
  });

  test('sem cofre e sem arquivo, o banco ainda guarda o login', () async {
    // O cenário exato do Ubuntu sem keyring e com `chmod` recusado.
    final store = DurableSecureStore(
      primary: _CofreIndisponivel(),
      fallback: _CamadaQueFalha(),
      extraFallbacks: [sqliteStore()],
    );

    await store.write('starchef_refresh_token', 'token-de-renovacao');

    expect(await store.read('starchef_refresh_token'), 'token-de-renovacao');
  });

  test('quando NENHUMA camada aceita, o chamador fica sabendo', () async {
    // O silêncio seria pior: o operador acharia que entrou e perderia a
    // sessão ao fechar, sem nenhum aviso.
    final store = DurableSecureStore(
      primary: _CofreIndisponivel(),
      fallback: _CamadaQueFalha(),
    );

    await expectLater(
      store.write('starchef_access_token', 'valor'),
      throwsA(anything),
    );
  });

  test('login offline funciona depois de reabrir o PDV', () async {
    final credenciais = DurableSecureStore(
      primary: _CofreIndisponivel(),
      fallback: _CamadaQueFalha(),
      extraFallbacks: [sqliteStore()],
    );
    await SecureOfflineLoginStore(
      valueStore: credenciais,
      // Menos iterações só para o teste rodar rápido; o produto usa 210 mil.
      passwordIterations: 1000,
    ).save(username: 'Ana', password: 'segredo', session: session);

    // Aplicativo reaberto: instâncias novas sobre o mesmo banco.
    final novoStore = SecureOfflineLoginStore(
      valueStore: DurableSecureStore(
        primary: _CofreIndisponivel(),
        fallback: _CamadaQueFalha(),
        extraFallbacks: [sqliteStore()],
      ),
      passwordIterations: 1000,
    );

    final restaurada = await novoStore.authenticate(
      // O nome do usuário é normalizado: quem digita "ANA" continua entrando.
      username: 'ANA',
      password: 'segredo',
    );

    expect(restaurada, isNotNull);
    expect(restaurada!.accessToken, 'token-de-acesso');
    expect(restaurada.user.restaurantId, 'rest-1');
  });

  test('senha errada continua sendo recusada offline', () async {
    final credenciais = DurableSecureStore(
      primary: _CofreIndisponivel(),
      extraFallbacks: [sqliteStore()],
      enablePlatformFallback: false,
    );
    final store = SecureOfflineLoginStore(
      valueStore: credenciais,
      passwordIterations: 1000,
    );
    await store.save(username: 'ana', password: 'segredo', session: session);

    expect(
      await store.authenticate(username: 'ana', password: 'errada'),
      isNull,
    );
  });

  test('o verificador guardado nunca contém a senha digitada', () async {
    final store = sqliteStore();
    await SecureOfflineLoginStore(
      valueStore: store,
      passwordIterations: 1000,
    ).save(username: 'ana', password: 'segredo-do-operador', session: session);

    final rows = await database.query('SELECT value FROM secure_values');

    expect(rows, isNotEmpty);
    for (final row in rows) {
      expect('${row['value']}', isNot(contains('segredo-do-operador')));
      // É um verificador PBKDF2, no mesmo formato do Django.
      expect('${row['value']}', contains('pbkdf2_sha256'));
    }
  });

  test('permissão restrita que falha não impede a gravação', () async {
    // Era exatamente isto que fazia o Ubuntu perder o login: `chmod`
    // indisponível (empacotamento restrito) ou recusado (volume exFAT, NFS)
    // abortava a escrita inteira. Um arquivo com a permissão padrão do
    // usuário é um risco menor do que o operador não conseguir entrar amanhã.
    final store = OwnerProtectedFileValueStore(
      directory: Directory(
        '${directory.path}${Platform.pathSeparator}secure',
      ),
      // Simula um sistema onde a mudança de modo não é aplicável.
      enforceModes: false,
    );

    await store.write('starchef_access_token', 'token');

    expect(await store.read('starchef_access_token'), 'token');
  });

  test('sair da sessão apaga a cópia do banco', () async {
    final store = sqliteStore();
    await store.write('starchef_access_token', 'token');

    await store.delete('starchef_access_token');

    expect(await store.read('starchef_access_token'), isNull);
  });

  test('valor ilegível equivale a ausente, sem travar a abertura', () async {
    // Acontece quando a chave do cofre muda entre reinstalações.
    await database.execute(
      '''
      INSERT INTO secure_values(value_key, value, updated_at)
      VALUES ('starchef_access_token', 'enc:v1:AAA:BBB:CCC', ?)
      ''',
      [DateTime.now().toUtc().toIso8601String()],
    );
    final store = SqliteSecureValueStore(
      database: database,
      cipher: PayloadCipher(store: _CofreEmMemoria()),
    );

    expect(await store.read('starchef_access_token'), isNull);
  });
}

/// Ubuntu sem Secret Service: toda operação falha.
class _CofreIndisponivel implements SecureValueStore {
  @override
  Future<void> delete(String key) async => throw const _SemCofre();

  @override
  Future<String?> read(String key) async => throw const _SemCofre();

  @override
  Future<void> write(String key, String value) async => throw const _SemCofre();
}

/// A cópia em arquivo recusando a gravação (volume que não aceita `chmod`,
/// diretório sem permissão).
class _CamadaQueFalha implements SecureValueStore {
  @override
  Future<void> delete(String key) async => throw const _SemCofre();

  @override
  Future<String?> read(String key) async => null;

  @override
  Future<void> write(String key, String value) async => throw const _SemCofre();
}

class _CofreEmMemoria implements SecureValueStore {
  final Map<String, String> _values = {};

  @override
  Future<void> delete(String key) async => _values.remove(key);

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async => _values[key] = value;
}

class _SemCofre implements Exception {
  const _SemCofre();

  @override
  String toString() => 'Cofre do sistema indisponível.';
}
