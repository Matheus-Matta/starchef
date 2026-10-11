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
}
