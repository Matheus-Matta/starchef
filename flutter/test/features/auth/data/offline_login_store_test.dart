import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/auth/data/offline_login_store.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'cofre guarda verificador e autentica sem persistir senha pura',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      const storage = FlutterSecureStorage();
      final store = SecureOfflineLoginStore(
        storage: storage,
        passwordIterations: 1000,
      );
      const session = AuthSession(
        accessToken: 'access',
        refreshToken: 'refresh',
        user: AuthUser(id: 'u1', username: 'ana', name: 'Ana'),
      );

      await store.save(
        username: 'Ana',
        password: 'segredo-local',
        session: session,
      );

      final rawValues = (await storage.readAll()).values.join('\n');
      expect(rawValues, isNot(contains('segredo-local')));
      expect(
        (await store.authenticate(
          username: 'ANA',
          password: 'segredo-local',
        ))?.user.id,
        'u1',
      );
      expect(
        await store.authenticate(username: 'ana', password: 'senha-errada'),
        isNull,
      );
    },
  );
}
