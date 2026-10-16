import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/api_exception.dart';
import 'package:starchef_pdv_mobile/core/network/cloud_fallback.dart';

/// Loja instável cai RÁPIDO para a nuvem e fica lá 5 minutos.
///
/// O garçom anda pelo salão e o Wi-Fi oscila. Com três sondas de 2 s e a
/// resposta perdida repetida na loja, o app ficava ~20 s parado antes de
/// desviar — com o cliente olhando.
void main() {
  test('uma sonda sem resposta ja basta para trocar de servidor', () async {
    var sondas = 0;
    final alvo = CloudFallback();
    final fora = await alvo.confirmarQuedaDoLocal(() async {
      sondas++;
      return false;
    });
    expect(fora, isTrue);
    expect(sondas, 1);
    expect(alvo.sondasAntesDeDesviar, 1);
  });

  test('tempo esgotado na loja ja e queda, sem sonda nenhuma', () async {
    var sondas = 0;
    final alvo = CloudFallback();
    final fora = await alvo.confirmarQuedaDoLocal(() async {
      sondas++;
      return true;
    }, lenta: true);
    expect(fora, isTrue);
    expect(sondas, 0, reason: 'loja lenta que responde ao /health/ não serve');
    expect(alvo.localForaDoAr, isTrue);
  });

  test('a nuvem espera mais que a loja', () {
    expect(ApiClient.timeoutLoja, const Duration(seconds: 8));
    expect(ApiClient.timeoutNuvem > ApiClient.timeoutLoja, isTrue);
  });

  group('escrita com tempo esgotado na loja', () {
    late List<String> caminho;

    ApiClient cliente() {
      caminho = [];
      return ApiClient(
        baseUrlProvider: () => 'http://loja.test/api/v1',
        httpClient: MockClient((request) async {
          caminho.add('${request.url.host}${request.url.path}');
          if (request.url.host == 'loja.test') {
            // Gravou (talvez) e a resposta se perdeu.
            throw TimeoutException('lenta');
          }
          return http.Response(jsonEncode({'id': 'x'}), 201);
        }),
        cloudFallback: CloudFallback(baseUrl: 'https://nuvem.test/api/v1'),
      )..configureSession(accessToken: 'a', refreshToken: 'r', terminalId: 't');
    }

    test('com id (UUID do aparelho) vai direto para a nuvem', () async {
      // As duas pontas gravam a MESMA linha; a sincronização junta.
      final api = cliente();
      await api.post(
        '/commands/c1/items/',
        body: {'id': 'uuid-1', 'product': 'p'},
        idempotencyKey: 'k1',
      );
      expect(caminho, [
        'loja.test/api/v1/commands/c1/items/',
        'nuvem.test/api/v1/commands/c1/items/',
      ]);
      expect(api.lastServerOrigin, ServerOrigin.nuvem);
    });

    test('sem id NAO repete na nuvem, mas a proxima ja vai para la', () async {
      // Repetir sem identidade num outro banco executaria duas vezes.
      final api = cliente();
      await expectLater(
        api.post(
          '/commands/c1/send-to-kitchen/',
          body: {},
          idempotencyKey: 'k2',
        ),
        throwsA(isA<ApiException>()),
      );
      expect(caminho.where((c) => c.startsWith('nuvem')), isEmpty);
      expect(api.cloudFallback.localForaDoAr, isTrue);

      caminho.clear();
      await api.get('/commands/');
      expect(caminho, ['nuvem.test/api/v1/commands/']);
    });
  });
}
