import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';

void main() {
  test('converte a resposta de login em uma sessão autenticada', () {
    final session = AuthSession.fromJson({
      'access': 'access-token',
      'refresh': 'refresh-token',
      'user': {
        'id': 'user-id',
        'username': 'manager',
        'name': 'Gerente',
        'branch_name': 'Matriz',
        'restaurant_name': 'StarChef',
      },
    });

    expect(session.accessToken, 'access-token');
    expect(session.refreshToken, 'refresh-token');
    expect(session.user.username, 'manager');
    expect(session.user.branchName, 'Matriz');
  });

  test('aceita nome ausente na resposta do usuário', () {
    final user = AuthUser.fromJson({
      'id': 'user-id',
      'username': 'operador',
      'name': null,
    });

    expect(user.name, isEmpty);
  });
}
