import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/errors/app_error_host.dart';
import 'package:starchef_pdv_desktop/core/errors/error_center.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/storage/local_preferences.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/scale/presentation/historico_de_passagens_dialog.dart';
import 'package:starchef_pdv_desktop/features/scale/presentation/scale_workstation_page.dart';

/// Recriada no meio do expediente, a estação volta LIGADA na mesma balança.
///
/// Erro, recarga ou troca de tela recriavam a Balança Rápida do zero, e ela
/// parava na escolha da balança: o operador tinha de escolher e iniciar de
/// novo a cada vez. Só a parada pedida pelo operador a deixa parada.
void main() {
  Future<List<bool>> abrir(
    WidgetTester tester,
    String? emUso, {
    bool esperarLigar = false,
  }) async {
    final directory = Directory.systemTemp.createTempSync('starchef-scale-');
    addTearDown(() => directory.deleteSync(recursive: true));
    final preferences = LocalPreferences(
      file: File('${directory.path}/preferences.json'),
    );
    // Arquivo de verdade: fora do relógio simulado do testWidgets.
    await tester.runAsync(() => preferences.setBalancaEmUso(emUso));
    final ligada = <bool>[];
    final servidor = MockClient((request) async {
      if (request.url.path.endsWith('/scales/')) {
        return http.Response(
          '{"results":[{"id":"b1","name":"Balança 1","product":"p1"},'
          '{"id":"b2","name":"Balança 2","product":"p1"}]}',
          200,
        );
      }
      return http.Response('{"results":[]}', 200);
    });
    tester.view.physicalSize = const Size(1920, 1080);
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
              client: servidor,
            ),
            accessToken: 'token',
            restaurants: const [
              {'id': 'r1', 'name': 'Unidade'},
            ],
            restaurantId: 'r1',
            products: const [
              {'id': 'p1', 'name': 'Comida por kg', 'pricing_unit': 'kg'},
            ],
            onRestaurantChanged: (_) async {},
            preferences: preferences,
            onRunningChanged: ligada.add,
          ),
        ),
      ),
    );
    // A leitura do vínculo do leitor é arquivo de verdade: o tempo real anda.
    // Quem espera LIGAR espera a condição (até ~3 s), não um tempo fixo: com a
    // suíte inteira disputando a CPU, 0,5 s às vezes não bastava e o teste
    // falhava sem defeito nenhum. Quem espera NÃO ligar dá as 5 voltas.
    for (var volta = 0; volta < (esperarLigar ? 30 : 5); volta++) {
      if (esperarLigar && ligada.contains(true)) break;
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 100)),
      );
      await tester.pump(const Duration(milliseconds: 200));
    }
    return ligada;
  }

  testWidgets('balanca em uso volta ligada ao recriar a tela', (tester) async {
    final ligada = await abrir(tester, 'r1:b2', esperarLigar: true);
    expect(ligada, contains(true));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('Tab abre as últimas passagens e Esc fecha', (tester) async {
    await abrir(tester, 'r1:b2', esperarLigar: true);

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    // A estação ligada tem um relógio de 1 s: nunca "assenta".
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(HistoricoDePassagensDialog), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.byType(HistoricoDePassagensDialog), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('sem balanca em uso, espera o operador escolher', (tester) async {
    final ligada = await abrir(tester, null);
    expect(ligada, isNot(contains(true)));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('balanca em uso de OUTRO restaurante nao liga aqui', (
    tester,
  ) async {
    final ligada = await abrir(tester, 'outro:b2');
    expect(ligada, isNot(contains(true)));
    await tester.pumpWidget(const SizedBox());
  });
}
