import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/storage/durable_secure_store.dart';
import 'package:starchef_pdv/core/storage/session_store.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp(
      'starchef-secure-fallback-',
    );
  });

  tearDown(() async {
    if (await directory.exists()) await directory.delete(recursive: true);
  });

  OwnerProtectedFileValueStore fileStore() =>
      OwnerProtectedFileValueStore(directory: directory, enforceModes: false);

  test('migra o valor existente no cofre nativo para o fallback', () async {
    final native = _MemoryValueStore({'token': 'valor-existente'});
    final first = DurableSecureStore(primary: native, fallback: fileStore());

    expect(await first.read('token'), 'valor-existente');

    final afterRestart = DurableSecureStore(
      primary: _UnavailableValueStore(),
      fallback: fileStore(),
    );
    expect(await afterRestart.read('token'), 'valor-existente');
  });

  test('fallback existente prevalece e repara um keyring antigo', () async {
    final fallback = fileStore();
    await fallback.write('pairing', 'chave-atual');
    final native = _MemoryValueStore({'pairing': 'chave-antiga'});
    final store = DurableSecureStore(primary: native, fallback: fallback);

    expect(await store.read('pairing'), 'chave-atual');
    expect(await native.read('pairing'), 'chave-atual');
  });

  test('falha ao migrar o fallback não esconde o valor do keyring', () async {
    final store = DurableSecureStore(
      primary: _MemoryValueStore({'token': 'valor-nativo'}),
      fallback: _UnavailableValueStore(),
    );

    expect(await store.read('token'), 'valor-nativo');
  });

  test('sessão sobrevive ao reinício sem Secret Service', () async {
    const session = AuthSession(
      accessToken: 'access-linux',
      refreshToken: 'refresh-linux',
      user: AuthUser(id: 'user-1', username: 'caixa', name: 'Caixa'),
    );
    final first = SecureSessionStore(
      valueStore: DurableSecureStore(
        primary: _UnavailableValueStore(),
        fallback: fileStore(),
      ),
    );
    await first.save(session);

    final afterRestart = SecureSessionStore(
      valueStore: DurableSecureStore(
        primary: _UnavailableValueStore(),
        fallback: fileStore(),
      ),
    );
    final restored = await afterRestart.read();

    expect(restored?.accessToken, session.accessToken);
    expect(restored?.refreshToken, session.refreshToken);
    expect(restored?.user.id, session.user.id);
  });

  test('logout remove também a cópia durável', () async {
    final fallback = fileStore();
    final store = DurableSecureStore(
      primary: _UnavailableValueStore(),
      fallback: fallback,
    );
    await store.write('session', 'valor');

    await store.delete('session');

    expect(await fallback.read('session'), isNull);
  });
}

class _MemoryValueStore implements SecureValueStore {
  _MemoryValueStore([Map<String, String>? values]) : values = {...?values};

  final Map<String, String> values;

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

class _UnavailableValueStore implements SecureValueStore {
  @override
  Future<void> delete(String key) => throw StateError('keyring indisponível');

  @override
  Future<String?> read(String key) => throw StateError('keyring indisponível');

  @override
  Future<void> write(String key, String value) =>
      throw StateError('keyring indisponível');
}
