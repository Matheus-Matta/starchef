import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/presentation/order_cart_panel.dart';

/// Numa conta com quatro comandas, o carrinho é uma lista só.
///
/// Sem dizer de qual cartão é cada linha, ninguém sabe o que pertence a quem —
/// e a conferência em voz alta com o cliente ("quanto é a minha?") não fecha.
///
/// E a anotação da comanda não se apaga daqui: ela não é deste carrinho, é
/// consumo que já existe no cartão. Um X daria a impressão de apagar o
/// consumo; o caminho certo é retirar a comanda inteira, no diálogo.
void main() {
  Map<String, dynamic> itemNovo() => {
    'id': 'l-1',
    'product_name': 'Coxinha',
    'quantity': 1,
    'unit_price': '6.00',
    'total_price': '6.00',
    'status': 'pending',
  };

  Map<String, dynamic> itemDeComanda() => {
    ...itemNovo(),
    'id': 'c-1',
    OrderDraftCart.marcaDeJaLancado: true,
    OrderDraftCart.marcaDaComanda: '12',
  };

  // `ShadCard` exige o tema do shadcn acima dele — a mesma moldura que os
  // outros testes de widget deste projeto usam.
  Widget carrinho(List<Map<String, dynamic>> itens) => MaterialApp(
    home: ShadTheme(
      data: AppTheme.shadLight(),
      child: Scaffold(
        body: SizedBox(
          width: 420,
          height: 900,
          child: OrderCartPanel(
            order: null,
            table: null,
            customer: null,
            printing: false,
            items: itens,
            money: (v) => 'R\$ $v',
            onVoidItem: (_) {},
            onFinish: () {},
            onSendToKitchen: () {},
            onPrint: () {},
            onCancel: () {},
            onChangeQuantity: (_, _) {},
          ),
        ),
      ),
    ),
  );

  testWidgets('item de comanda diz de QUAL comanda é', (tester) async {
    await tester.pumpWidget(carrinho([itemDeComanda()]));

    expect(find.text('Comanda 12'), findsOneWidget);
  });

  testWidgets('item passado agora nao ganha selo de comanda', (tester) async {
    await tester.pumpWidget(carrinho([itemNovo()]));

    expect(find.textContaining('Comanda'), findsNothing);
  });

  testWidgets('item de comanda NAO oferece o botao de remover', (tester) async {
    await tester.pumpWidget(carrinho([itemDeComanda()]));

    expect(find.byTooltip('Remover item'), findsNothing);
  });
}
