import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/cloud_mode_banner.dart';

/// O garçom precisa SABER quando quem está atendendo é a nuvem.
///
/// Não é um detalhe de rede: é uma mudança de onde o lançamento está sendo
/// gravado. Enquanto a loja está fora, outro aparelho que ainda a alcance
/// enxerga um salão diferente — e a nota fiscal simplesmente não sai.
void main() {
  Widget tela(ServerOrigin origem) =>
      MaterialApp(home: Scaffold(body: CloudModeBanner(origin: origem)));

  testWidgets('avisa quando quem atende e a nuvem', (tester) async {
    await tester.pumpWidget(tela(ServerOrigin.nuvem));

    expect(find.textContaining('NUVEM'), findsOneWidget);
  });

  testWidgets('diz que nota fiscal e caixa ficam indisponiveis', (
    tester,
  ) async {
    // Eles não desviam de propósito: dois emissores de número de nota, ou duas
    // sessões no mesmo turno, não se resolvem com sincronização. Sem o aviso,
    // o garçom descobre quando a nota não sai.
    await tester.pumpWidget(tela(ServerOrigin.nuvem));

    final texto = tester
        .widget<Text>(find.textContaining('NUVEM'))
        .data!
        .toLowerCase();

    expect(texto, contains('nota'));
    expect(texto, contains('caixa'));
    expect(texto, contains('volt'), reason: 'e que o que ele lançou desce depois');
  });

  testWidgets('atendendo pela loja o aviso nao ocupa espaco', (tester) async {
    await tester.pumpWidget(tela(ServerOrigin.loja));

    expect(find.byType(Text), findsNothing);
    expect(tester.getSize(find.byType(CloudModeBanner)), Size.zero);
  });
}
