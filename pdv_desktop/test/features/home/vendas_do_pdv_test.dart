import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_commands.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_materializer.dart';
import 'package:starchef_pdv_desktop/features/orders/data/previa_local.dart';

/// Vendas de verdade montadas no PDV, com o total que ele calcula SOZINHO.
///
/// É a metade do PDV de um contrato: o backend (`test_vendas_do_pdv.py`) manda
/// as MESMAS vendas ao `/orders/submit/` com este total e exige que o servidor
/// aceite. Um centavo de diferença e a venda voltava "total mudou" no caixa —
/// foi o que este teste achou no buffet por quilo (0,500 kg × 10,05 = 5,025:
/// em `double` vira 5,0249… e o PDV dava 5,02; o servidor, 5,03).
void main() {
  final tabela =
      jsonDecode(File('test/fixtures/vendas_do_pdv.json').readAsStringSync())
          as Map<String, dynamic>;
  final produtos = (tabela['produtos'] as Map).cast<String, dynamic>();
  final vendas = (tabela['vendas'] as List).cast<Map<String, dynamic>>();

  OrderDraftCart montar(Map<String, dynamic> venda) {
    final draft = OrderDraftCart();
    var anotacao = 0;
    for (final comanda in (venda['comandas'] as List? ?? const [])) {
      final numero = comanda['numero'];
      draft.attachCommand(
        {'id': 'c$numero', 'number': numero},
        items: [
          // O que `/commands/{id}/items/` devolve: o total já é do servidor.
          for (final item in comanda['anotacoes'] as List)
            {
              'id': 'a${++anotacao}',
              'product_name': item['produto'],
              'total_price': produtos[item['produto']]['preco'],
            },
        ],
      );
    }
    var n = 0;
    for (final linha in venda['linhas'] as List) {
      final produto = produtos[linha['produto']] as Map;
      final peso = linha['peso_kg'] == null
          ? null
          : double.parse('${linha['peso_kg']}');
      draft.add(
        OrderDraftLine(
          id: 'l${++n}',
          productId: '${linha['produto']}',
          productName: '${linha['produto']}',
          quantity: peso ?? (linha['quantidade'] as num).toDouble(),
          unitPrice: double.parse('${produto['preco']}'),
          weightKg: peso,
          pricingUnit: peso == null ? null : 'kg',
        ),
      );
    }
    return draft;
  }

  /// A tela de pagamento: a prévia e, por cima, o que o operador mexeu.
  Map<String, dynamic> pagamento(
    OrderDraftCart draft,
    Map<String, dynamic> venda,
  ) {
    final previa = previaLocal(draft, percentualDaTaxa: venda['taxa']);
    final ajustes = (venda['ajustes'] as Map).cast<String, dynamic>();
    if (ajustes.isEmpty) return previa;
    return FechamentoLocal.aplicar(previa, {
      'service_fee_enabled': true,
      'discount': '0.00',
      ...ajustes,
    }, percentualDaTaxa: venda['taxa']);
  }

  for (final venda in vendas) {
    test('o PDV fecha "${venda['nome']}" em ${venda['total']}', () {
      final draft = montar(venda);

      expect(podeAbrirNaHora(draft), isTrue, reason: 'abre sem esperar');
      expect(pagamento(draft, venda)['total'], venda['total']);
    });
  }

  test(
    'o Concluir leva o total do PDV, os pesos e as anotacoes vistas',
    () async {
      final venda = vendas.firstWhere(
        (v) => v['nome'] == 'comanda com buffet pesado e taxa',
      );
      final draft = montar(venda);
      final tela = pagamento(draft, venda);
      draft.anotacoesVistas = anotacoesVistas(draft);
      Map<String, dynamic>? enviado;
      final api = ApiClient(
        baseUrl: 'http://loja.local/api/v1',
        cloudFallback: CloudFallback(enabled: false),
        client: MockClient((request) async {
          enviado = jsonDecode(request.body) as Map<String, dynamic>;
          return http.Response('{"order": {}, "payments": []}', 201);
        }),
      );

      await OrderDraftMaterializer(
        api,
        accessToken: 'x.eyJ1c2VyX2lkIjoidTEifQ.y',
      ).concluir(
        draft,
        restaurantId: 'r1',
        fechamento: {'service_fee_enabled': true, 'discount': '0.00'},
        recebimentos: const [],
        totalMostrado: '${tela['total']}',
      );

      expect(enviado!['expected_total'], '61.92');
      expect(enviado!['command_items'], ['a1']);
      final item = (enviado!['items'] as List).single as Map;
      expect(item['weight_kg'], '0.731');
      await api.dispose();
    },
  );
}
