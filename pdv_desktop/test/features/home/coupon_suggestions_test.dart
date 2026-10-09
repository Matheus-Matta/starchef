import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/coupon_suggestions.dart';

/// Os cupons como botões no pagamento: os mais usados de cara e, digitando,
/// a busca. Um toque aplica — sem abrir nada, sem digitar o código inteiro.
void main() {
  late List<Uri> chamadas;

  ApiClient api() {
    chamadas = [];
    return ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((request) async {
        chamadas.add(request.url);
        final busca = request.url.queryParameters['search'] ?? '';
        final todos = ['BEMVINDO', 'NATAL10', 'NATALVIP', 'FRETE'];
        final achados = todos.where(
          (c) => c.toLowerCase().contains(busca.toLowerCase()),
        );
        return http.Response(
          jsonEncode({
            'results': [
              for (final c in achados) {'code': c, 'name': ''},
            ],
          }),
          200,
        );
      }),
    );
  }

  Future<List<String>> montar(
    WidgetTester tester,
    TextEditingController campo,
    List<String> aplicados,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CouponSuggestions(
            api: api(),
            accessToken: 't',
            controller: campo,
            onPick: aplicados.add,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    return aplicados;
  }

  testWidgets('mostra os mais usados e um toque aplica', (tester) async {
    final aplicados = await montar(tester, TextEditingController(), []);

    expect(
      chamadas.single.queryParameters,
      containsPair('ordering', '-total_resgates'),
    );
    expect(chamadas.single.queryParameters, containsPair('vigentes', '1'));
    expect(chamadas.single.queryParameters, containsPair('page_size', '5'));
    await tester.tap(find.text('NATAL10'));
    expect(aplicados, ['NATAL10']);
  });

  testWidgets('digitar busca pelo que foi digitado, uma vez só por pausa', (
    tester,
  ) async {
    final campo = TextEditingController();
    await montar(tester, campo, []);

    campo.text = 'n';
    await tester.pump(const Duration(milliseconds: 100));
    campo.text = 'nat';
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();

    expect(chamadas.map((u) => u.queryParameters['search']), [null, 'nat']);
    expect(find.text('NATAL10'), findsOneWidget);
    expect(find.text('NATALVIP'), findsOneWidget);
    expect(find.text('FRETE'), findsNothing);
  });
}
