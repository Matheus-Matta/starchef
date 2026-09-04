import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/features/auth/domain/waiter_session.dart';

void main() {
  test('perfil fixo Garçom não recebe pagamento sem permissão extra', () {
    final waiter = WaiterUser.fromJson({
      'id': 'user-id',
      'username': 'garcom',
      'name': 'Garçom',
      'account_id': 'account-id',
      'restaurant_id': 'restaurant-id',
      'profile_type': 'waiter',
      'permissions': [
        'orders.view.own',
        'orders.create',
        'orders.manage',
        'tables.view',
        'tables.manage',
        'menu.view',
        'customers.view',
        'kitchen.view',
      ],
    });

    expect(waiter.canReceivePayment, isFalse);
  });

  test('garçom com payments.manage liberado à parte recebe pagamento', () {
    final waiter = WaiterUser.fromJson({
      'id': 'user-id',
      'username': 'garcom-caixa',
      'name': 'Garçom Caixa',
      'account_id': 'account-id',
      'restaurant_id': 'restaurant-id',
      'profile_type': 'waiter',
      'permissions': ['orders.view.own', 'payments.manage'],
    });

    expect(waiter.canReceivePayment, isTrue);
  });

  test('sem lista de permissões na resposta, não recebe pagamento', () {
    final waiter = WaiterUser.fromJson({
      'id': 'user-id',
      'username': 'garcom',
      'name': 'Garçom',
      'account_id': 'account-id',
      'restaurant_id': 'restaurant-id',
    });

    expect(waiter.permissions, isEmpty);
    expect(waiter.canReceivePayment, isFalse);
  });
}
