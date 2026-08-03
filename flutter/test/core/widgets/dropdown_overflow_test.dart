import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Reproduz a caixa de seleção "Situação" da tela de Pedidos.
///
/// O PDV amplia o texto até 1,22× conforme a largura da janela, e o rótulo
/// mais longo não cabe na caixa de 230 px sem `isExpanded`. Sem esse ajuste o
/// `RenderFlex` interno do `InputDecorator` estoura à direita e o operador
/// perde parte do texto.
Widget _statusFilter({required bool isExpanded, required double textScale}) =>
    MaterialApp(
      home: Scaffold(
        body: MediaQuery(
          data: MediaQueryData(textScaler: TextScaler.linear(textScale)),
          child: Row(
            children: [
              const Expanded(child: SizedBox()),
              SizedBox(
                width: 230,
                child: DropdownButtonFormField<String>(
                  initialValue: 'pending',
                  isExpanded: isExpanded,
                  decoration: const InputDecoration(labelText: 'Situação'),
                  items: const [
                    DropdownMenuItem(
                      value: 'pending',
                      child: Text(
                        'Pendentes de pagamento',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    DropdownMenuItem(
                      value: 'all',
                      child: Text('Todos'),
                    ),
                  ],
                  onChanged: (_) {},
                ),
              ),
              const SizedBox(width: 12),
              IconButton.filledTonal(
                onPressed: () {},
                icon: const Icon(Icons.refresh),
              ),
            ],
          ),
        ),
      ),
    );

void main() {
  testWidgets('o filtro de situação não estoura com o texto ampliado', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _statusFilter(isExpanded: true, textScale: 1.22),
    );
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Pendentes de pagamento'), findsOneWidget);
  });

  testWidgets('sem isExpanded o mesmo rótulo estoura — guarda a regressão', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      _statusFilter(isExpanded: false, textScale: 1.22),
    );
    await tester.pump();

    // Este é exatamente o defeito relatado em produção. O teste existe para
    // provar que a correção acima é a que resolve, e não outra coisa.
    final error = tester.takeException();
    expect(error, isA<FlutterError>());
    expect('$error', contains('overflowed'));
  });
}
