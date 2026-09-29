import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/update/manual_update_action.dart';
import 'package:starchef_pdv_mobile/core/update/mobile_update_service.dart';

class _UpdatedService extends MobileUpdateService {
  var disposed = false;

  @override
  Future<MobileUpdateStatus> check() async =>
      const MobileUpdateStatus(phase: UpdatePhase.upToDate, installed: '1.2.2');

  @override
  void dispose() => disposed = true;
}

void main() {
  final ordersPage = File(
    'lib/features/orders/presentation/orders_page.dart',
  ).readAsStringSync();
  final accountMenu = File(
    'lib/features/orders/presentation/orders_page_components.dart',
  ).readAsStringSync();

  test('sessao restaurada tambem verifica atualizacao no salao', () {
    expect(ordersPage, contains('UpdateBanner('));
  });

  test('menu da conta oferece busca manual de atualizacao', () {
    expect(accountMenu, contains("'updates'"));
    expect(ordersPage, contains('checkMobileUpdateNow'));
  });

  testWidgets('busca manual informa quando o aplicativo esta atualizado', (
    tester,
  ) async {
    final service = _UpdatedService();
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => FilledButton(
              onPressed: () => checkMobileUpdateNow(context, service: service),
              child: const Text('Buscar'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Buscar'));
    await tester.pumpAndSettle();

    expect(find.textContaining('já está atualizado (1.2.2)'), findsOneWidget);
    expect(service.disposed, isFalse);
  });
}
