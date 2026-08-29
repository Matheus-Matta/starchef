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

  group('perfis fixos (Garçom/Caixa/Gerente/Administrador)', () {
    AuthUser userWith(List<String> permissions, {String? profileType}) =>
        AuthUser(
          id: 'user-id',
          username: 'operador',
          name: 'Operador',
          profileType: profileType,
          permissions: permissions,
        );

    test('garçom não acessa caixa, não cancela pedido e não recebe pagamento', () {
      final waiter = userWith([
        'orders.view.own',
        'orders.create',
        'orders.manage',
        'tables.view',
        'tables.manage',
        'menu.view',
        'customers.view',
        'kitchen.view',
      ], profileType: 'waiter');

      expect(waiter.canAccessCash, isFalse);
      expect(waiter.canCancelOrders, isFalse);
      expect(waiter.canProcessPayments, isFalse);
    });

    test('caixa acessa o financeiro e processa pagamentos, mas não cancela pedido', () {
      final cashier = userWith([
        'orders.view',
        'cash.view.own',
        'cash.open',
        'cash.close.own',
        'cash.manage.own',
        'cash.withdrawal',
        'cash.supply',
        'payments.manage',
      ], profileType: 'cashier');

      expect(cashier.canAccessCash, isTrue);
      expect(cashier.canProcessPayments, isTrue);
      expect(cashier.canCancelOrders, isFalse);
      expect(cashier.canManageDevices, isFalse);
    });

    test('gerente cancela pedido e gerencia dispositivos', () {
      final manager = userWith([
        'orders.cancel',
        'cash.manage',
        'devices.manage',
      ], profileType: 'manager');

      expect(manager.canCancelOrders, isTrue);
      expect(manager.canAccessCash, isTrue);
      expect(manager.canManageDevices, isTrue);
    });

    test('coringa "*" libera tudo, mesmo sem profileType admin', () {
      final wildcard = userWith(['*']);

      expect(wildcard.canAccessCash, isTrue);
      expect(wildcard.canCancelOrders, isTrue);
      expect(wildcard.canProcessPayments, isTrue);
      expect(wildcard.canManageDevices, isTrue);
    });
  });
}
