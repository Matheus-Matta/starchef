import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/cash/domain/cash_restaurant_selector.dart';

void main() {
  test('prioriza o restaurante do caixa ativo vinculado ao usuário', () {
    final selected = cashLinkedRestaurantId(
      userId: 'user-2',
      availableRestaurantIds: const {'restaurant-1', 'restaurant-2'},
      cashStations: const [
        {
          'id': 'cash-1',
          'restaurant': 'restaurant-1',
          'operators': ['user-1'],
          'is_active': true,
        },
        {
          'id': 'cash-2',
          'restaurant': 'restaurant-2',
          'operators': ['user-2'],
          'is_active': true,
        },
      ],
    );

    expect(selected, 'restaurant-2');
  });

  test('ignora caixa inativo e restaurante fora das unidades disponíveis', () {
    final selected = cashLinkedRestaurantId(
      userId: 'user-1',
      availableRestaurantIds: const {'restaurant-1'},
      cashStations: const [
        {
          'restaurant': 'restaurant-1',
          'operators': ['user-1'],
          'is_active': false,
        },
        {
          'restaurant': 'restaurant-2',
          'operators': [
            {'id': 'user-1'},
          ],
          'is_active': true,
        },
      ],
    );

    expect(selected, isNull);
  });

  test('aceita referências enriquecidas com id', () {
    final selected = cashLinkedRestaurantId(
      userId: 'user-1',
      availableRestaurantIds: const {'restaurant-3'},
      cashStations: const [
        {
          'restaurant': {'id': 'restaurant-3'},
          'operators': [
            {'id': 'user-1'},
          ],
        },
      ],
    );

    expect(selected, 'restaurant-3');
  });
}
