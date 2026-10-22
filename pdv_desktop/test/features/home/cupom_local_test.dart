import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/home/data/cupom_local.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/previa_local.dart';

/// O cupom da venda nova: o servidor CONFERE, o PDV faz a conta.
///
/// Digitar um cupom simulava a venda inteira no servidor (60 a 120 consultas)
/// e travava a tela em "Calculando total". Agora vai uma pergunta só, com os
/// números da venda, e o total é refeito aqui.
void main() {
  late List<http.Request> pedidos;

  ApiClient api(Map<String, dynamic> resposta) => ApiClient(
    baseUrl: 'http://loja.local/api/v1',
    cloudFallback: CloudFallback(enabled: false),
    client: MockClient((request) async {
      pedidos.add(request);
      return http.Response(
        jsonEncode(resposta),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }),
  );

  OrderDraftCart venda() => OrderDraftCart()
    ..add(
      const OrderDraftLine(
        id: 'l1',
        productId: 'p-prato',
        productName: 'Prato',
        quantity: 4,
        unitPrice: 50,
      ),
    );

  setUp(() => pedidos = []);

  test('o desconto conferido entra no total feito no PDV', () async {
    final draft = venda();
    final previa = previaLocal(draft, percentualDaTaxa: '10');

    final pedido = await aplicarCupomLocal(
      api({
        'valid': true,
        'discount': '15.00',
        'coupon': {'code': 'DEZ'},
      }),
      accessToken: 't',
      codigo: 'dez',
      pedido: previa,
      fechamento: const {'service_fee_enabled': true},
      draft: draft,
      percentualDaTaxa: '10',
    );

    // 200 + 10% de taxa − 15 de cupom.
    expect(pedido['total'], '205.00');
    expect(pedido['coupon_code'], 'DEZ');
    expect(pedido['coupon_discount'], '15.00');
    expect(pedidos, hasLength(1));
    expect(pedidos.single.url.path, endsWith('/promotions/coupons/validate/'));
    final corpo = jsonDecode(pedidos.single.body) as Map;
    expect(corpo['subtotal'], '200.00');
    expect(corpo['products'], ['p-prato']);
  });

  test('a recusa traz a frase do servidor e o total não muda', () async {
    final draft = venda();

    expect(
      () => aplicarCupomLocal(
        api({'valid': false, 'reason': 'Este CPF já usou este cupom.'}),
        accessToken: 't',
        codigo: 'UMAVEZ',
        pedido: previaLocal(draft, percentualDaTaxa: '10'),
        fechamento: const {},
        draft: draft,
        percentualDaTaxa: '10',
      ),
      throwsA(
        isA<CupomRecusado>().having(
          (e) => e.motivo,
          'motivo',
          'Este CPF já usou este cupom.',
        ),
      ),
    );
  });

  test('retirar o cupom não vai ao servidor', () async {
    final draft = venda();
    final comCupom = {
      ...previaLocal(draft, percentualDaTaxa: '10'),
      'coupon_code': 'DEZ',
      'coupon_discount': '15.00',
    };

    final pedido = await aplicarCupomLocal(
      api(const {}),
      accessToken: 't',
      codigo: '',
      pedido: comCupom,
      fechamento: const {'service_fee_enabled': true},
      draft: draft,
      percentualDaTaxa: '10',
    );

    expect(pedidos, isEmpty);
    expect(pedido['coupon_code'], '');
    expect(pedido['total'], '220.00');
  });
  test(
    'servidor antigo (sem conferência sem pedido) pede o caminho de antes',
    () async {
      // O backend anterior só conferia cupom de pedido salvo e respondia 400
      // "Informe o pedido a conferir." O PDV volta à simulação no servidor, que
      // funciona em qualquer versão, em vez de mostrar esse erro no campo.
      final draft = venda();
      final antigo = ApiClient(
        baseUrl: 'http://loja.local/api/v1',
        cloudFallback: CloudFallback(enabled: false),
        client: MockClient(
          (request) async => http.Response(
            jsonEncode({'detail': 'Informe o pedido a conferir.'}),
            400,
            headers: {'content-type': 'application/json; charset=utf-8'},
          ),
        ),
      );

      expect(
        () => aplicarCupomLocal(
          antigo,
          accessToken: 't',
          codigo: 'DEZ',
          pedido: previaLocal(draft, percentualDaTaxa: '10'),
          fechamento: const {},
          draft: draft,
          percentualDaTaxa: '10',
        ),
        throwsA(isA<ConferenciaSemPedidoIndisponivel>()),
      );
    },
  );
}
