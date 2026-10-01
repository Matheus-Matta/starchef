import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error_host.dart';
import 'package:starchef_pdv_desktop/core/errors/error_center.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/storage/local_preferences.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/scale/presentation/scale_workstation_page.dart';

/// Respostas que não são erro de API, mas que a tela recebia sem tratamento.
///
/// Antes, cada uma escapava como `TypeError` de um `Future` sem `catch`: a
/// Balança Rápida ficava em "carregando" para sempre, sem dizer o motivo.
final _respostasEstranhas = <String, http.Response>{
  'lista com itens que não são objetos': http.Response(
    '{"results":[1,2]}',
    200,
  ),
  'results que não é lista': http.Response('{"results":"x"}', 200),
};

void main() {
  for (final caso in _respostasEstranhas.entries) {
    testWidgets('balança rápida mostra o erro em vez de travar: ${caso.key}', (
      tester,
    ) async {
      await _abrirBalanca(tester, (_) async => caso.value);

      expect(tester.takeException(), isNull);
      // Balanças e impressoras carregam juntas; a última falha fica na tela.
      expect(
        find.textContaining(RegExp('Balanças:|Impressoras:')),
        findsOneWidget,
      );
    });
  }

  testWidgets('erro de API continua aparecendo como antes', (tester) async {
    await _abrirBalanca(
      tester,
      (_) async => http.Response('{"detail":"negado"}', 403),
    );

    expect(tester.takeException(), isNull);
  });
}

Future<void> _abrirBalanca(
  WidgetTester tester,
  Future<http.Response> Function(http.Request) servidor,
) async {
  final directory = Directory.systemTemp.createTempSync('starchef-scale-');
  addTearDown(() => directory.deleteSync(recursive: true));
  tester.view.physicalSize = const Size(1280, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark(),
      builder: (context, child) => ShadTheme(
        data: AppTheme.shadDark(),
        child: AppErrorHost(center: ErrorCenter(), child: child!),
      ),
      home: Scaffold(
        body: ScaleWorkstationPage(
          api: ApiClient(
            baseUrl: 'http://starchef.test/api/v1',
            client: MockClient(servidor),
          ),
          accessToken: 'token',
          restaurants: const [
            {'id': 'r1', 'name': 'Unidade'},
          ],
          restaurantId: 'r1',
          products: const [],
          onRestaurantChanged: (_) async {},
          preferences: LocalPreferences(
            file: File('${directory.path}/preferences.json'),
          ),
        ),
      ),
    ),
  );
  await tester.pump(const Duration(seconds: 1));
}
