import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/comanda_card.dart';
import 'package:starchef_pdv_mobile/features/orders/presentation/comanda_resumo.dart';

/// O cartão da grade mostra O QUE a comanda tem, sem o garçom abri-la.
///
/// Antes ele só sabia QUANTOS itens: para achar "a comanda do X-Burger" o
/// garçom abria cartão por cartão.
void main() {
  test('unidade com "x", quilo com vírgula, e o resto vira +N', () {
    expect(
      resumoDaComanda({
        'items': [
          {'name': 'X-Burger', 'quantity': '3', 'unit': 'unit'},
          {'name': 'Picanha', 'quantity': '0.35', 'unit': 'kg'},
        ],
        'more': 2,
      }),
      '3x X-Burger · 0,35 kg Picanha · +2',
    );
  });

  test('livre, sem resumo (lista sem ?preview) ou torto: vazio', () {
    expect(resumoDaComanda({'items': [], 'more': 0}), '');
    expect(resumoDaComanda(null), '');
    expect(resumoDaComanda('x'), '');
  });

  testWidgets(
    'o cartão em uso mostra o resumo; o livre continua "Sem consumo"',
    (tester) async {
      Future<void> mostrar(Map<String, dynamic> comanda) => tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              width: 200,
              height: 150,
              child: ComandaCard(command: comanda, onTap: () {}),
            ),
          ),
        ),
      );

      await mostrar({
        'number': 12,
        'pending_items': 3,
        'pending_total': '45.00',
        'pending_preview': {
          'items': [
            {'name': 'X-Burger', 'quantity': '3', 'unit': 'unit'},
          ],
          'more': 0,
        },
      });
      expect(find.text('3x X-Burger'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await mostrar({'number': 13, 'pending_items': 0});
      expect(find.text('Sem consumo'), findsOneWidget);
    },
  );
}
