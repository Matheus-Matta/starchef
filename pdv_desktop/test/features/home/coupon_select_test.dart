import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/coupon_select.dart';

/// O cupom do pagamento é UM campo de seleção com busca.
///
/// Eram um campo, um botão "Aplicar" e uma fileira de botões com os cupons
/// soltos embaixo: três controles para uma escolha só, e a fileira empurrava o
/// resumo da conta. Agora a lista abre no próprio campo — "Nenhum" sempre em
/// primeiro, os vigentes logo abaixo, a busca enquanto digita — e o X remove.
void main() {
  late List<String> eventos;

  ApiClient api() => ApiClient(
    baseUrl: 'http://loja.local/api/v1',
    client: MockClient((request) async {
      final busca = request.url.queryParameters['search'] ?? '';
      final todos = ['BEMVINDO10', 'MENOS5', 'NATAL10'];
      return http.Response(
        jsonEncode({
          'results': [
            for (final c in todos.where(
              (c) => c.toLowerCase().contains(busca.toLowerCase()),
            ))
              {'code': c, 'name': 'Cupom $c'},
          ],
        }),
        200,
      );
    }),
  );

  Future<void> montar(WidgetTester tester, {String aplicado = ''}) {
    eventos = [];
    return tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark(),
        home: Scaffold(
          body: CouponSelect(
            api: api(),
            accessToken: 't',
            aplicado: aplicado,
            busy: false,
            erro: '',
            onAplicar: (codigo) => eventos.add('aplicar:$codigo'),
            onRemover: () => eventos.add('remover'),
          ),
        ),
      ),
    );
  }

  Future<void> abrir(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('payment-coupon')));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();
  }

  testWidgets('ao abrir mostra Nenhum primeiro e os cupons vigentes', (
    tester,
  ) async {
    await montar(tester);
    await abrir(tester);

    final nenhum = tester.getTopLeft(find.text('Nenhum')).dy;
    expect(tester.getTopLeft(find.text('BEMVINDO10')).dy, greaterThan(nenhum));
    expect(find.text('MENOS5'), findsOneWidget);
  });

  testWidgets('digitar filtra pela busca do servidor', (tester) async {
    await montar(tester);
    await abrir(tester);

    await tester.enterText(find.byKey(const Key('payment-coupon')), 'nat');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pumpAndSettle();

    expect(find.text('NATAL10'), findsOneWidget);
    expect(find.text('MENOS5'), findsNothing);
    expect(find.text('Nenhum'), findsOneWidget); // sempre lá
  });

  testWidgets('escolher um cupom aplica', (tester) async {
    await montar(tester);
    await abrir(tester);

    await tester.tap(find.text('MENOS5'));
    await tester.pumpAndSettle();

    expect(eventos, ['aplicar:MENOS5']);
  });

  testWidgets('escolher Nenhum remove o cupom aplicado', (tester) async {
    await montar(tester, aplicado: 'NATAL10');
    await abrir(tester);

    await tester.tap(find.text('Nenhum'));
    await tester.pumpAndSettle();

    expect(eventos, ['remover']);
  });

  testWidgets('o X dentro do campo remove o cupom', (tester) async {
    await montar(tester, aplicado: 'NATAL10');

    expect(find.byKey(const Key('payment-coupon-remove')), findsOneWidget);
    await tester.tap(find.byKey(const Key('payment-coupon-remove')));
    await tester.pumpAndSettle();

    expect(eventos, ['remover']);
  });

  testWidgets('sem cupom aplicado nao ha X', (tester) async {
    await montar(tester);

    expect(find.byKey(const Key('payment-coupon-remove')), findsNothing);
  });

  testWidgets('codigo digitado e Enter aplica, mesmo fora da lista', (
    tester,
  ) async {
    await montar(tester);
    await abrir(tester);

    await tester.enterText(find.byKey(const Key('payment-coupon')), 'vip50');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(eventos, ['aplicar:VIP50']);
  });
}
