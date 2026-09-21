import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_cloud_banner.dart';

/// O operador precisa SABER que a loja caiu e quem está atendendo é a nuvem.
///
/// Não é um detalhe de rede: é uma mudança de onde a venda está sendo gravada.
/// Sem a faixa, dois terminais do mesmo salão — um na loja, outro na nuvem —
/// acham que estão vendo a mesma coisa.
void main() {
  Widget tela({required bool visivel}) =>
      MaterialApp(home: Scaffold(body: PdvCloudBanner(visible: visivel)));

  testWidgets('a faixa aparece quando quem atende e a nuvem', (tester) async {
    await tester.pumpWidget(tela(visivel: true));

    expect(find.textContaining('nuvem'), findsOneWidget);
  });

  testWidgets('a faixa avisa que fiscal e caixa ficam indisponiveis', (
    tester,
  ) async {
    // Eles não desviam de propósito: dois emissores de número de nota, ou duas
    // sessões no mesmo turno, não se resolvem com sincronização. O operador
    // descobriria isso quando a nota não saísse.
    await tester.pumpWidget(tela(visivel: true));

    final texto = tester.widget<Text>(find.textContaining('nuvem')).data ?? '';
    expect(texto.toLowerCase(), contains('nota fiscal'));
    expect(texto.toLowerCase(), contains('caixa'));
  });

  testWidgets('no caminho normal a faixa nao ocupa espaco', (tester) async {
    await tester.pumpWidget(tela(visivel: false));

    expect(find.textContaining('nuvem'), findsNothing);
    expect(tester.getSize(find.byType(PdvCloudBanner)), Size.zero);
  });

  group('o estado de rede', () {
    test('a fase da nuvem CONTA como ter conexao', () {
      // Quem atende é a nuvem, mas há conexão: marcar como offline faria a
      // tela recusar gestos que estão funcionando.
      const status = NetworkStatus(phase: NetworkPhase.cloud);

      expect(status.hasConnection, isTrue);
      expect(status.servidoPelaNuvem, isTrue);
    });

    test('o caminho normal NAO e servido pela nuvem', () {
      const status = NetworkStatus(phase: NetworkPhase.online);

      expect(status.servidoPelaNuvem, isFalse);
    });
  });
}
