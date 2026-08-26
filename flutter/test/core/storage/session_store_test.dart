import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/storage/session_store.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('uses the child-process session when the OS vault is empty', () async {
    const fallback = AuthSession(
      accessToken: 'access-from-parent',
      refreshToken: 'refresh-from-parent',
      user: AuthUser(id: 'user-1', username: 'caixa', name: 'Caixa'),
    );
    final store = SecureSessionStore(
      storage: const FlutterSecureStorage(),
      initialSession: fallback,
    );

    final restored = await store.read();

    expect(restored?.accessToken, fallback.accessToken);
    expect(restored?.refreshToken, fallback.refreshToken);
    expect(restored?.user.id, fallback.user.id);
  });

  test(
    'the child-process session is authoritative and consumed once',
    () async {
      const inherited = AuthSession(
        accessToken: 'fallback-access',
        refreshToken: 'fallback-refresh',
        user: AuthUser(id: 'fallback', username: 'fallback', name: 'Fallback'),
      );
      const stored = AuthSession(
        accessToken: 'stored-access',
        refreshToken: 'stored-refresh',
        user: AuthUser(id: 'stored', username: 'stored', name: 'Stored'),
      );
      final store = SecureSessionStore(
        storage: const FlutterSecureStorage(),
        initialSession: inherited,
      );
      await store.save(stored);

      final firstRead = await store.read();
      final secondRead = await store.read();

      expect(firstRead?.accessToken, inherited.accessToken);
      expect(firstRead?.user.id, inherited.user.id);
      expect(secondRead?.accessToken, stored.accessToken);
      expect(secondRead?.user.id, stored.user.id);
    },
  );
}
