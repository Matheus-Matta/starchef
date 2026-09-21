import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_materializer.dart';

/// A hora em que o rascunho vira pedido de verdade.
///
/// O caso que faltava era o CENTRAL do modelo novo: a mesa com dois cartões
/// que chega no caixa para pagar. O operador não tem nada para passar — o
/// consumo já está anotado nos cartões —, e o PDV recusava com "Não há itens
/// para abrir o pedido". A conta simplesmente não abria.
void main() {
  late List<({String caminho, Map<String, dynamic> corpo})> enviados;

  OrderDraftMaterializer materializador() {
    enviados = [];
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient((request) async {
        enviados.add((
          caminho: request.url.path.replaceFirst('/api/v1', ''),
          corpo: request.body.isEmpty
              ? <String, dynamic>{}
              : Map<String, dynamic>.from(jsonDecode(request.body) as Map),
        ));
        return http.Response('{"id": "order-1", "items": []}', 200);
      }),
    );
    return OrderDraftMaterializer(api, accessToken: 'token');
  }

  OrderDraftLine linha() => const OrderDraftLine(
    id: 'l-1',
    productId: 'p1',
    productName: 'Coxinha',
    quantity: 1,
    unitPrice: 6,
  );

  OrderDraftCart comComandas(List<String> ids) {
    final draft = OrderDraftCart();
    for (final id in ids) {
      draft.commands.add({'id': id, 'number': id});
    }
    return draft;
  }

  test('SO comandas abre a conta, sem exigir item novo', () async {
    final alvo = materializador();

    await alvo.materialize(comComandas(['c-1', 'c-2']), restaurantId: 'rest-1');

    expect(enviados.map((e) => e.caminho).toList(), [
      '/orders/',
      '/orders/order-1/attach-commands/',
    ]);
    expect(enviados.first.corpo['order_type'], 'command');
    expect(enviados.first.corpo['restaurant'], 'rest-1');
    expect(enviados.last.corpo['commands'], ['c-1', 'c-2']);
  });

  test('so comandas NAO passa por create-with-item', () async {
    // `create-with-item` é atômico porque LEVA um item. Sem item ele não tem
    // o que criar, e chamá-lo assim seria pedir 400 ao servidor.
    final alvo = materializador();

    await alvo.materialize(comComandas(['c-1']), restaurantId: 'rest-1');

    expect(
      enviados.map((e) => e.caminho),
      isNot(contains('/orders/create-with-item/')),
    );
  });

  test('rascunho vazio de TUDO continua sendo recusado', () async {
    // Sem item e sem comanda não existe conta para abrir, e criar um pedido
    // vazio aqui encheria o banco do que ninguém vai pagar.
    final alvo = materializador();

    await expectLater(
      alvo.materialize(OrderDraftCart(), restaurantId: 'rest-1'),
      throwsA(isA<ApiException>()),
    );
    expect(enviados, isEmpty);
  });

  test('com item o pedido nasce COM ele, numa transacao so', () async {
    final alvo = materializador();
    final draft = OrderDraftCart()..add(linha());

    await alvo.materialize(draft, restaurantId: 'rest-1');

    expect(enviados.single.caminho, '/orders/create-with-item/');
    expect(enviados.single.corpo['order_type'], 'counter');
  });

  test('item MAIS comanda grava o pedido como de comanda', () async {
    // Os dois PDVs precisam gravar o mesmo formato: um pedido com tipo
    // diferente conforme o caixa em que foi aberto quebra qualquer relatório
    // que agrupe por tipo.
    final alvo = materializador();
    final draft = comComandas(['c-1'])..add(linha());

    await alvo.materialize(draft, restaurantId: 'rest-1');

    expect(enviados.first.caminho, '/orders/create-with-item/');
    expect(enviados.first.corpo['order_type'], 'command');
  });
}
