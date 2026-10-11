import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_materializer.dart';

/// A venda sai do PDV num envio só (`POST /orders/submit/`).
///
/// Antes eram uma chamada para criar o pedido, uma por item, uma para anexar
/// as comandas e uma por recebimento: uma troca loja/nuvem no meio deixava
/// metade da venda em cada servidor. Agora o rascunho inteiro — com os
/// recebimentos, quando há — vai num payload, e tudo leva o UUID do PDV.
void main() {
  late List<({String caminho, Map<String, dynamic> corpo})> enviados;

  OrderDraftMaterializer materializador() {
    enviados = [];
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient((request) async {
        enviados.add((
          caminho: request.url.path.replaceFirst('/api/v1', ''),
          corpo: Map<String, dynamic>.from(jsonDecode(request.body) as Map),
        ));
        return http.Response(
          '{"order": {"id": "order-1", "items": []}, "payments": [], "created": true}',
          201,
        );
      }),
    );
    return OrderDraftMaterializer(api, accessToken: 'token');
  }

  OrderDraftCart rascunho({List<String> comandas = const [], int linhas = 0}) {
    final draft = OrderDraftCart();
    for (final id in comandas) {
      draft.commands.add({'id': id, 'number': id});
    }
    for (var i = 0; i < linhas; i++) {
      draft.add(
        OrderDraftLine(
          id: '',
          productId: 'p$i',
          productName: 'Produto $i',
          quantity: 1,
          unitPrice: 6,
        ),
      );
    }
    return draft;
  }

  test(
    'itens e comandas vao num envio so, com o UUID do pedido e das linhas',
    () async {
      final alvo = materializador();
      final draft = rascunho(comandas: ['c-1', 'c-2'], linhas: 2);

      await alvo.materialize(draft, restaurantId: 'rest-1', cozinha: true);

      expect(enviados.map((e) => e.caminho).toList(), ['/orders/submit/']);
      final corpo = enviados.single.corpo;
      expect(corpo['id'], draft.orderId);
      expect(corpo['order_type'], 'command');
      expect(corpo['commands'], ['c-1', 'c-2']);
      expect(corpo['kitchen'], isA<Map>());
      final idsDasLinhas = [
        for (final l in corpo['items'] as List) (l as Map)['id'],
      ];
      expect(idsDasLinhas, [for (final l in draft.lines) l.id]);
      expect(
        idsDasLinhas.every((id) => RegExp(r'^[0-9a-f-]{36}$').hasMatch('$id')),
        isTrue,
      );
    },
  );

  test(
    'o reenvio leva o MESMO id: o servidor reconhece a mesma venda',
    () async {
      final alvo = materializador();
      final draft = rascunho(linhas: 1);

      await alvo.materialize(draft, restaurantId: 'rest-1');
      await alvo.materialize(draft, restaurantId: 'rest-1');

      expect(enviados[0].corpo['id'], enviados[1].corpo['id']);
      expect(enviados[0].corpo['items'], enviados[1].corpo['items']);
    },
  );

  test('simular pede o total com o fechamento, sem gravar', () async {
    final alvo = materializador();

    await alvo.simular(
      rascunho(linhas: 1),
      restaurantId: 'rest-1',
      fechamento: {'service_fee_enabled': true},
    );

    final corpo = enviados.single.corpo;
    expect(corpo['simular'], isTrue);
    expect(corpo['close'], {'service_fee_enabled': true});
    expect(corpo.containsKey('payments'), isFalse);
  });

  // A senha de ações do caixa aprova o desconto de quem não é gerente. Ia
  // só no `/close/`; na venda nova o caixa ficava sem como dar desconto.
  test(
    'a senha que aprova o desconto vai na simulacao e na conclusao',
    () async {
      final alvo = materializador();
      final draft = rascunho(linhas: 1);

      await alvo.simular(draft, restaurantId: 'r', senhaDoCaixa: '1234');
      await alvo.concluir(
        draft,
        restaurantId: 'r',
        recebimentos: const [],
        senhaDoCaixa: '1234',
      );
      await alvo.simular(draft, restaurantId: 'r');

      expect(enviados[0].corpo['cash_password'], '1234');
      expect(enviados[1].corpo['cash_password'], '1234');
      expect(enviados[2].corpo.containsKey('cash_password'), isFalse);
    },
  );

  test('concluir manda pedido, fechamento e recebimentos juntos', () async {
    final alvo = materializador();
    final draft = rascunho(comandas: ['c-1']);

    final resposta = await alvo.concluir(
      draft,
      restaurantId: 'rest-1',
      fechamento: {'fiscal_customer_cpf': '52998224725'},
      recebimentos: [
        {'id': 'pg-1', 'payment_method': 'pix', 'amount': '10.00'},
      ],
    );

    final corpo = enviados.single.corpo;
    expect(corpo['payments'], [
      {'id': 'pg-1', 'payment_method': 'pix', 'amount': '10.00'},
    ]);
    expect(corpo['close'], {'fiscal_customer_cpf': '52998224725'});
    expect(corpo['kitchen'], isA<Map>());
    expect(resposta['order']['id'], 'order-1');
  });

  test('a conclusao leva so as anotacoes que o caixa viu', () async {
    // O garçom lançou na comanda enquanto o cliente pagava: sem a lista, a
    // conta fechava com um total maior que o recebido.
    final alvo = materializador();
    final draft = rascunho(comandas: ['c-1'])..anotacoesVistas = ['a-1'];

    await alvo.concluir(draft, restaurantId: 'rest-1', recebimentos: const []);

    expect(enviados.single.corpo['command_items'], ['a-1']);
  });

  test('sem simular, nao restringe as anotacoes', () async {
    final alvo = materializador();

    await alvo.materialize(rascunho(comandas: ['c-1']), restaurantId: 'rest-1');

    expect(enviados.single.corpo.containsKey('command_items'), isFalse);
  });

  test('sem item e sem comanda nao ha o que abrir', () async {
    final alvo = materializador();

    expect(
      () => alvo.materialize(OrderDraftCart(), restaurantId: 'rest-1'),
      throwsA(isA<ApiException>()),
    );
    expect(enviados, isEmpty);
  });
}
