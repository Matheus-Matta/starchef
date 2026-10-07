import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/storage/offline_queue_store.dart';
import 'package:starchef_pdv_mobile/core/sync/backend_gateway.dart';
import 'package:starchef_pdv_mobile/core/theme/app_theme.dart';
import 'package:starchef_pdv_mobile/features/auth/domain/waiter_session.dart';
import 'package:starchef_pdv_mobile/features/menu/presentation/product_picker_sheet.dart';
import 'package:starchef_pdv_mobile/features/orders/data/orders_repository.dart';

/// Lançar a mesa inteira sem fechar o cardápio a cada prato.
void main() {
  OrdersRepository repositorio() {
    final api = ApiClient(
      baseUrlProvider: () => 'http://loja.local/api/v1',
      httpClient: MockClient((request) async {
        final produtos = request.url.path.endsWith('/menu/products/');
        return http.Response(
          jsonEncode({
            'next': null,
            'results': produtos
                ? [
                    {'id': 'coca', 'name': 'Coca', 'current_price': '6.00'},
                    {
                      'id': 'burger',
                      'name': 'Burger',
                      'current_price': '25.00',
                      'variations': [
                        {'id': 'v1', 'name': 'Duplo', 'is_active': true},
                      ],
                    },
                  ]
                : [],
          }),
          200,
        );
      }),
    );
    return OrdersRepository(
      api: api,
      gateway: BackendGateway(api: api, store: OfflineQueueStore()),
      session: WaiterSession(
        accessToken: 'a',
        refreshToken: 'r',
        user: WaiterUser(
          id: 'u',
          username: 'g',
          name: 'G',
          accountId: 'c',
          restaurantId: 'r',
        ),
      ),
    );
  }

  testWidgets(
    'produto simples entra com um toque e o cardápio continua aberto',
    (tester) async {
      final escolhidos = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) =>
              ShadTheme(data: AppTheme.shadLight(), child: child!),
          home: Scaffold(
            body: ProductPicker(
              repository: repositorio(),
              onChoose: (choice) async => escolhidos.add(choice.productId),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Coca'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Coca'));
      await tester.pumpAndSettle();

      expect(escolhidos, ['coca', 'coca']);
      expect(find.text('2 item(ns) adicionado(s)'), findsOneWidget);
      expect(find.text('Concluir'), findsOneWidget);
    },
  );

  testWidgets(
    'produto com variação abre a configuração em vez de entrar direto',
    (tester) async {
      final escolhidos = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          builder: (context, child) =>
              ShadTheme(data: AppTheme.shadLight(), child: child!),
          home: Scaffold(
            body: ProductPicker(
              repository: repositorio(),
              onChoose: (choice) async => escolhidos.add(choice.productId),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Burger'));
      await tester.pumpAndSettle();

      expect(escolhidos, isEmpty);
      expect(find.text('Duplo'), findsWidgets);
    },
  );
}
