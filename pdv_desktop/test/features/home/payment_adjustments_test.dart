import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/payment_adjustments.dart';

/// Taxa, documento da nota e desconto DENTRO da tela de pagamento.
///
/// Ficavam num modal antes dela: o caixa decidia a taxa e o CPF sem ver o
/// total, e para mudar qualquer coisa depois tinha de voltar e refazer o
/// fechamento na frente do cliente.
void main() {
  late List<Object> chamadas;

  Future<void> montar(
    WidgetTester tester, {
    bool cobrarTaxa = true,
    String documento = '',
    int desconto = 0,
    int maxDesconto = 10000,
    bool bloqueado = false,
  }) {
    chamadas = [];
    return tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: PaymentAdjustments(
            cobrarTaxa: cobrarTaxa,
            rotuloTaxa: '10% · R\$ 12,36',
            documento: documento,
            documentoControle: TextEditingController(),
            descontoCentavos: desconto,
            maxDescontoCentavos: maxDesconto,
            busy: false,
            bloqueado: bloqueado,
            erro: '',
            onTaxa: (valor) => chamadas.add('taxa:$valor'),
            onDocumento: (valor) => chamadas.add('doc:$valor'),
            onDesconto: (valor) => chamadas.add('desconto:$valor'),
          ),
        ),
      ),
    );
  }

  Finder campo(String chave) => find.byKey(Key(chave));

  testWidgets('a chave tira e poe a taxa de servico', (tester) async {
    await montar(tester);

    await tester.tap(campo('payment-service-fee'));
    await tester.pump();

    expect(chamadas, ['taxa:false']);
    expect(find.textContaining('10%'), findsOneWidget);
  });

  testWidgets('CPF valido vai so com os digitos', (tester) async {
    await montar(tester);

    await tester.enterText(campo('payment-document'), '529.982.247-25');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(chamadas, ['doc:52998224725']);
  });

  testWidgets('o mesmo campo aceita CNPJ', (tester) async {
    await montar(tester);

    await tester.enterText(campo('payment-document'), '11.222.333/0001-81');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(chamadas, ['doc:11222333000181']);
  });

  testWidgets('documento invalido avisa no campo e nao envia', (tester) async {
    await montar(tester);

    await tester.enterText(campo('payment-document'), '111.111.111-11');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(chamadas, isEmpty);
    expect(find.textContaining('inválido'), findsOneWidget);
  });

  testWidgets('apagar o documento tira ele da nota', (tester) async {
    await montar(tester, documento: '52998224725');

    await tester.enterText(campo('payment-document'), '');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(chamadas, ['doc:']);
  });

  testWidgets('desconto digitado entra pelos centavos', (tester) async {
    await montar(tester);

    await tester.enterText(campo('payment-discount'), '1250');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(chamadas, ['desconto:1250']);
  });

  testWidgets('desconto acima do subtotal nao e enviado', (tester) async {
    await montar(tester, maxDesconto: 1000);

    await tester.enterText(campo('payment-discount'), '5000');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(chamadas, isEmpty);
    expect(find.textContaining('subtotal'), findsOneWidget);
  });

  testWidgets('com pagamento lancado, nada muda o total', (tester) async {
    await montar(tester, bloqueado: true);

    await tester.tap(campo('payment-service-fee'));
    await tester.pump();

    expect(chamadas, isEmpty);
    expect(find.textContaining('Remova os pagamentos'), findsOneWidget);
  });

  // Aplicado, o botão do campo vira um X: o gesto que sobra é REMOVER, e
  // tirar o CPF ou o desconto não exige apagar o texto à mão.
  testWidgets('CPF aplicado mostra o X, e o X tira o documento', (
    tester,
  ) async {
    await montar(tester, documento: '52998224725');

    expect(campo('payment-document-remove'), findsOneWidget);
    await tester.tap(campo('payment-document-remove'));
    await tester.pump();

    expect(chamadas, ['doc:']);
  });

  testWidgets('desconto aplicado mostra o X, e o X zera o desconto', (
    tester,
  ) async {
    await montar(tester, desconto: 250);

    expect(campo('payment-discount-remove'), findsOneWidget);
    await tester.tap(campo('payment-discount-remove'));
    await tester.pump();

    expect(chamadas, ['desconto:0']);
  });

  testWidgets('sem nada aplicado nao ha X', (tester) async {
    await montar(tester);

    expect(campo('payment-document-remove'), findsNothing);
    expect(campo('payment-discount-remove'), findsNothing);
  });

  testWidgets('editando o valor aplicado, volta o botao de aplicar', (
    tester,
  ) async {
    await montar(tester, desconto: 250);

    await tester.enterText(campo('payment-discount'), '500');
    await tester.pump();

    expect(campo('payment-discount-remove'), findsNothing);
  });

  testWidgets(
    'o campo abre com o documento do pedido, não com o texto da venda anterior',
    (tester) async {
      // O controle agora é da tela (o "Adicionar pagamento" lê o texto): o
      // CPF digitado e não aplicado na venda anterior entraria na nota desta.
      final controle = TextEditingController(text: '529.982.247-25');
      addTearDown(controle.dispose);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PaymentAdjustments(
              cobrarTaxa: true,
              rotuloTaxa: '10%',
              documento: '',
              documentoControle: controle,
              descontoCentavos: 0,
              maxDescontoCentavos: 1000,
              busy: false,
              bloqueado: false,
              erro: '',
              onTaxa: (_) {},
              onDocumento: (_) {},
              onDesconto: (_) {},
            ),
          ),
        ),
      );

      expect(controle.text, isEmpty);
    },
  );
}
