import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/security/cash_password.dart';
import 'package:starchef_pdv/core/storage/session_store.dart';
import 'package:starchef_pdv/features/auth/data/auth_repository.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';
import 'package:starchef_pdv/features/auth/presentation/auth_controller.dart';
import 'package:starchef_pdv/features/cash/data/cash_auth_repository.dart';
import 'package:starchef_pdv/features/cash/data/cash_auth_store.dart';

class _MemorySessionStore implements SessionStore {
  @override
  Future<void> clear() async {}

  @override
  Future<AuthSession?> read() async => null;

  @override
  Future<void> save(AuthSession session) async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'fechamento usa senha do restaurante e fallback apenas sem cadastro',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      const secureStorage = FlutterSecureStorage();
      final api = ApiClient(baseUrl: 'http://starchef.test/api/v1');
      final cashStore = CashAuthStore(storage: secureStorage);
      final cashAuth = CashAuthRepository(apiClient: api, store: cashStore);
      final controller = AuthController(
        AuthRepository(
          apiClient: api,
          sessionStore: _MemorySessionStore(),
          cashAuth: cashAuth,
        ),
      );

      expect(
        await controller.verifySupervisorClosePassword('12345678'),
        isTrue,
      );

      controller.activeRestaurantId = 'restaurant-1';
      await cashStore.saveHash(
        'restaurant-1',
        await CashPassword.encode('senha-restaurante', iterations: 1000),
      );

      expect(
        await controller.verifySupervisorClosePassword('senha-restaurante'),
        isTrue,
      );
      expect(
        await controller.verifySupervisorClosePassword('12345678'),
        isFalse,
      );

      controller.dispose();
      await api.dispose();
    },
  );
}
