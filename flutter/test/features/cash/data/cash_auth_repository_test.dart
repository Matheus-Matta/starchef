import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/security/cash_password.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';
import 'package:starchef_pdv/features/cash/data/cash_auth_repository.dart';
import 'package:starchef_pdv/features/cash/data/cash_auth_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test(
    'reload substitui imediatamente o hash antigo guardado em memoria',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      const storage = FlutterSecureStorage();
      final oldHash = await CashPassword.encode(
        'senha-antiga',
        iterations: 1000,
      );
      final newHash = await CashPassword.encode('senha-nova', iterations: 1000);
      final store = CashAuthStore(storage: storage);
      await store.saveHash('restaurant-1', oldHash);
      final api = ApiClient(
        baseUrl: 'http://starchef.test/api/v1',
        client: MockClient(
          (_) async => http.Response(
            jsonEncode({
              'algorithm': 'pbkdf2_sha256',
              'has_password': true,
              'password_hash': newHash,
            }),
            200,
            headers: {'content-type': 'application/json'},
          ),
        ),
      );
      final repository = CashAuthRepository(apiClient: api, store: store);
      const session = AuthSession(
        accessToken: 'token',
        refreshToken: 'refresh',
        user: AuthUser(
          id: 'user-1',
          username: 'operador',
          name: 'Operador',
          restaurantId: 'restaurant-1',
        ),
      );

      expect(
        await repository.verify('senha-antiga', restaurantId: 'restaurant-1'),
        isTrue,
      );
      expect(await repository.trySync(session), isTrue);
      expect(
        await repository.verify('senha-antiga', restaurantId: 'restaurant-1'),
        isFalse,
      );
      expect(
        await repository.verify('senha-nova', restaurantId: 'restaurant-1'),
        isTrue,
      );

      await api.dispose();
    },
  );
}
