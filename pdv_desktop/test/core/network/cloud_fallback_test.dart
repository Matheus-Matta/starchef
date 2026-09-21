import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';

/// As regras que impedem a venda duplicada quando o terminal troca de servidor.
///
/// A loja roda o próprio backend. Se ela cai, o terminal desvia para a nuvem —
/// e é aí que mora o risco: a deduplicação por `Idempotency-Key` vive no banco
/// de CADA backend, então uma operação que a loja já gravou, repetida na nuvem,
/// executaria de novo.
///
/// Cada teste abaixo é uma dessas regras.
void main() {
  final conexaoRecusada = ApiException(
    'sem conexão',
    isConnectivity: true,
  );
  final tempoEsgotado = ApiException(
    'o servidor demorou demais',
    isConnectivity: true,
    reachedServer: true,
  );

  group('o que faz o terminal desviar', () {
    test('leitura desvia quando a conexao e recusada', () {
      expect(CloudFallback().deveTentar('GET', '/orders/', conexaoRecusada), isTrue);
    });

    test('leitura desvia em 502, 503 e 504', () {
      // O proxy respondeu; o backend atrás dele, não.
      for (final status in [502, 503, 504]) {
        expect(
          CloudFallback().deveTentar('GET', '/orders/', ApiException('x', statusCode: status)),
          isTrue,
          reason: '$status significa que a requisição não chegou ao backend',
        );
      }
    });

    test('500 puro NAO desvia', () {
      // 500 é defeito de UM endpoint, não "o backend caiu". Desviar mandaria o
      // terminal inteiro para a nuvem por causa de uma rota com bug — e lá ele
      // encontraria o mesmo bug, porque é o mesmo código.
      expect(
        CloudFallback().deveTentar('GET', '/orders/', ApiException('x', statusCode: 500)),
        isFalse,
      );
    });

    test('recusa do servidor NAO desvia', () {
      // 400, 403, 409: o backend está de pé e disse não. A nuvem diria o mesmo.
      for (final status in [400, 401, 403, 404, 409, 422]) {
        expect(
          CloudFallback().deveTentar('GET', '/orders/', ApiException('x', statusCode: status)),
          isFalse,
        );
      }
    });
  });

  group('a escrita desvia — menos quando pode ter sido executada', () {
    test('escrita desvia quando a conexao e recusada', () {
      // Ninguém recebeu nada: não há o que duplicar.
      expect(CloudFallback().deveTentar('POST', '/orders/', conexaoRecusada), isTrue);
    });

    test('escrita NAO desvia quando o tempo esgotou', () {
      // A REGRA que impede a cobrança dupla. O servidor pode ter gravado e só
      // a resposta ter se perdido; repetir na nuvem cobraria de novo, porque a
      // chave que a loja consumiu a nuvem nunca viu.
      //
      // Essa escrita espera na fila, que reenvia para a MESMA loja com a mesma
      // chave — e lá a deduplicação funciona.
      expect(CloudFallback().deveTentar('POST', '/orders/', tempoEsgotado), isFalse);
    });

    test('leitura desvia mesmo com tempo esgotado', () {
      // Ler duas vezes não duplica nada.
      expect(CloudFallback().deveTentar('GET', '/orders/', tempoEsgotado), isTrue);
    });

    test('todo metodo de escrita segue a mesma regra', () {
      for (final metodo in ['POST', 'PUT', 'PATCH', 'DELETE']) {
        expect(CloudFallback().deveTentar(metodo, '/orders/', conexaoRecusada), isTrue);
        expect(CloudFallback().deveTentar(metodo, '/orders/', tempoEsgotado), isFalse);
      }
    });
  });

  group('so desvia com a queda CONFIRMADA', () {
    test('a loja respondendo a sonda impede o desvio', () async {
      // Um pacote perdido ou um reinício de dois segundos do serviço não podem
      // mudar o servidor do terminal inteiro.
      final fallback = CloudFallback();

      final fora = await fallback.confirmarQuedaDoLocal(() async => true);

      expect(fora, isFalse);
      expect(fallback.localForaDoAr, isFalse);
    });

    test('a sonda falhando confirma a queda', () async {
      final fallback = CloudFallback();

      final fora = await fallback.confirmarQuedaDoLocal(() async => false);

      expect(fora, isTrue);
      expect(fallback.localForaDoAr, isTrue);
    });

    test('confirmada a queda, nao sonda de novo na janela', () async {
      // Bater na loja morta a cada chamada custaria o tempo do `timeout` em
      // cada gesto do operador.
      final fallback = CloudFallback();
      await fallback.confirmarQuedaDoLocal(() async => false);

      var sondou = false;
      final fora = await fallback.confirmarQuedaDoLocal(() async {
        sondou = true;
        return true;
      });

      expect(fora, isTrue);
      expect(sondou, isFalse, reason: 'o veredito vale pela janela');
    });

    test('a loja respondendo esquece o veredito', () async {
      // É assim que o terminal VOLTA sozinho quando a loja sobe.
      final fallback = CloudFallback();
      await fallback.confirmarQuedaDoLocal(() async => false);

      fallback.localRespondeu();

      expect(fallback.localForaDoAr, isFalse);
    });
  });

  group('o endereco da nuvem', () {
    test('e fixo em compilacao e HTTPS', () {
      // É o último recurso quando a loja está fora, e um endereço que o técnico
      // pode digitar errado no cadastro não serve como último recurso.
      expect(CloudFallback.enderecoDaNuvem, startsWith('https://'));
      expect(CloudFallback.enderecoDaNuvem, contains('api.starchef.com.br'));
    });

    test('monta o mesmo caminho com a mesma consulta', () {
      final uri = CloudFallback().enderecoPara('/orders/', {'page': 2});

      expect(uri.scheme, 'https');
      expect(uri.host, 'api.starchef.com.br');
      expect(uri.path, '/api/v1/orders/');
      expect(uri.queryParameters['page'], '2');
    });
  });

  group('desligavel', () {
    test('terminal de rede fechada nunca sai da loja', () {
      final fallback = CloudFallback(enabled: false);

      expect(fallback.deveTentar('GET', '/orders/', conexaoRecusada), isFalse);
      expect(fallback.deveTentar('POST', '/orders/', conexaoRecusada), isFalse);
    });
  });

  group('o que NUNCA sai da loja', () {
    test('fiscal nao desvia, nem para leitura', () {
      // O número da nota é sequencial dentro de uma SÉRIE, e a série é o
      // mecanismo legal para separar pontos de emissão. Dois nós na mesma
      // série produzem duas notas com o mesmo número — a SEFAZ rejeita a
      // segunda, ou aceita e sobra para o contador desfazer.
      final fallback = CloudFallback();

      expect(fallback.deveTentar('GET', '/invoices/', conexaoRecusada), isFalse);
      expect(
        fallback.deveTentar('POST', '/invoices/emit/', conexaoRecusada),
        isFalse,
      );
    });

    test('caixa nao desvia', () {
      // Abrir sessão na nuvem com a loja tendo a dela dá dois saldos de
      // abertura no mesmo turno, e nenhum relatório diz qual vale.
      final fallback = CloudFallback();

      expect(
        fallback.deveTentar('POST', '/cash-register/open/', conexaoRecusada),
        isFalse,
      );
      expect(
        fallback.deveTentar('GET', '/cash-register/current/', conexaoRecusada),
        isFalse,
      );
    });

    test('a protecao e por PREFIXO, entao rota nova nasce protegida', () {
      final fallback = CloudFallback();

      expect(fallback.nuncaDesvia('/invoices/qualquer-coisa-nova/'), isTrue);
      expect(fallback.nuncaDesvia('/cash-register/seja-la-o-que-for/'), isTrue);
      // E o resto continua desviando.
      expect(fallback.nuncaDesvia('/orders/'), isFalse);
      expect(fallback.nuncaDesvia('/commands/13/items/'), isFalse);
    });
  });
}
