import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/data/local_id.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_cart.dart';
import 'package:starchef_pdv_desktop/features/orders/data/order_draft_materializer.dart';

/// Quanto do tempo da venda é do PRÓPRIO PDV: montar o JSON, o cliente HTTP
/// (desvio, repetição, cache) e decodificar a resposta.
///
/// A montagem roda sempre. A ida ao servidor só com `MEDIR_URL` (ex.:
/// http://127.0.0.1:8012/api/v1): compara o tempo visto aqui com o
/// `Server-Timing` do Django — a diferença é o PDV mais a rede.
///
///   MEDIR_URL=http://127.0.0.1:8012/api/v1 flutter test test/medicao
void main() {
  OrderDraftCart rascunho(List<Map<String, dynamic>> produtos, int itens) {
    final draft = OrderDraftCart();
    for (var n = 0; n < itens; n++) {
      final produto = produtos[n % produtos.length];
      draft.add(
        OrderDraftLine(
          // Vazio: o carrinho dá o UUID. A nota distinta impede que linhas do
          // mesmo produto se juntem — são N itens de verdade.
          id: '',
          customerNote: 'item $n',
          productId: '${produto['id']}',
          productName: '${produto['name']}',
          quantity: 1,
          unitPrice: double.tryParse('${produto['sale_price'] ?? 10}') ?? 10,
        ),
      );
    }
    return draft;
  }

  test(
    'montar e codificar o JSON da venda leva menos de 5 ms com 50 itens',
    () {
      final produtos = [
        for (var n = 0; n < 30; n++)
          {'id': 'p$n', 'name': 'Produto $n', 'sale_price': '9.90'},
      ];
      final materializador = OrderDraftMaterializer(
        ApiClient(
          baseUrl: 'http://x',
          cloudFallback: CloudFallback(enabled: false),
        ),
        accessToken: 't',
      );
      for (final itens in [1, 10, 50]) {
        final relogio = Stopwatch()..start();
        for (var volta = 0; volta < 200; volta++) {
          jsonEncode(
            materializador.corpo(
              rascunho(produtos, itens),
              restaurantId: 'r1',
              cozinha: true,
            ),
          );
        }
        final porVenda = relogio.elapsedMicroseconds / 200 / 1000;
        // ignore: avoid_print
        print(
          'montar+codificar $itens itens: ${porVenda.toStringAsFixed(3)} ms',
        );
        expect(porVenda, lessThan(5));
      }
    },
  );

  final url = Platform.environment['MEDIR_URL'] ?? '';
  test(
    'venda real: PDV x servidor',
    () async {
      final api = ApiClient(
        baseUrl: url,
        cloudFallback: CloudFallback(enabled: false),
      );
      final sessao = await api.post(
        '/auth/login/',
        body: {
          'username': Platform.environment['MEDIR_USUARIO'] ?? 'admin',
          'password': Platform.environment['MEDIR_SENHA'] ?? 'admin12345',
          'no_cookie': true,
        },
      );
      final token = '${sessao['access']}';
      final restaurantes = await api.get('/restaurants/', accessToken: token);
      final restaurante = '${(restaurantes['results'] as List).first['id']}';
      final produtos = [
        for (final p
            in (await api.get(
                  '/menu/products/',
                  query: {
                    'restaurant': restaurante,
                    'is_active': true,
                    'page_size': 300,
                  },
                  accessToken: token,
                ))['results']
                as List)
          if (p['pricing_unit'] != 'kg' &&
              p['is_weighed'] != true &&
              p['requires_variation'] != true)
            Map<String, dynamic>.from(p as Map),
      ];
      final metodos =
          (await api.get(
                '/payments/methods/',
                query: {'restaurant': restaurante},
                accessToken: token,
              ))['results']
              as List;
      final dinheiro =
          '${metodos.firstWhere((m) => m['method_type'] == 'cash')['id']}';
      final materializador = OrderDraftMaterializer(api, accessToken: token);

      for (final itens in [1, 10, 50]) {
        final linhas = <String>[];
        for (var volta = 0; volta < 6; volta++) {
          final draft = rascunho(produtos, itens);
          var relogio = Stopwatch()..start();
          final previa = await materializador.simular(
            draft,
            restaurantId: restaurante,
            fechamento: {'discount': 0},
          );
          final simularMs = relogio.elapsedMilliseconds;
          final servidorSimular = api.ultimoServerTiming;
          relogio = Stopwatch()..start();
          await materializador.concluir(
            draft,
            restaurantId: restaurante,
            fechamento: {'discount': 0},
            totalMostrado: '${previa['total']}',
            recebimentos: [
              {
                'id': LocalId.uuid(),
                'payment_method': dinheiro,
                'amount': '${previa['total']}',
                'client_updated_at': DateTime.now().toUtc().toIso8601String(),
              },
            ],
          );
          final concluirMs = relogio.elapsedMilliseconds;
          if (volta == 0) continue; // aquece
          linhas.add(
            'simular ${simularMs}ms [$servidorSimular] | '
            'concluir ${concluirMs}ms [${api.ultimoServerTiming}]',
          );
        }
        // ignore: avoid_print
        print('--- $itens itens\n${linhas.join('\n')}');
      }
    },
    skip: url.isEmpty ? 'sem MEDIR_URL' : false,
    timeout: const Timeout(Duration(minutes: 5)),
  );
}
