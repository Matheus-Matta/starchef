import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/auth/data/login_pela_nuvem.dart';

/// No login, o PDV pega na NUVEM o IP do server local do restaurante.
///
/// O IP era digitado em cada terminal, e mudar o servidor da loja era refazer
/// isso caixa por caixa. Agora o login passa pela nuvem (fixa), lê
/// `/pdv/config/` e entra na loja com o mesmo usuário e senha.
void main() {
  const nuvem = 'https://nuvem.test/api/v1';
  const loja = 'http://192.168.0.10/api/v1';

  late List<String> chamadas;
  late String? ipGuardado;
  late Set<String> foraDoAr;
  late String ipDaConfig;
  late String nuvemDaConfig;

  http.Client servidores() => MockClient((request) async {
    final base = '${request.url.scheme}://${request.url.authority}';
    chamadas.add('$base${request.url.path}');
    if (foraDoAr.contains(base)) {
      throw http.ClientException('Connection refused', request.url);
    }
    if (request.url.path.endsWith('/pdv/config/')) {
      return http.Response(
        jsonEncode({
          'restaurant': 'r1',
          'ip_server_local': ipDaConfig,
          'ip_server_nuvem': nuvemDaConfig,
        }),
        200,
      );
    }
    final origem = base.contains('nuvem') ? 'nuvem' : 'loja';
    return http.Response(
      jsonEncode({'access': 'token-$origem', 'refresh': 'r', 'user': {}}),
      200,
    );
  });

  Future<(Map<String, dynamic>, ApiClient)> entrar({
    String baseInicial = nuvem,
  }) async {
    final cliente = servidores();
    // O cliente do PDV COMO EM PRODUÇÃO: com o desvio automático para a
    // nuvem ligado. Usado no login, ele levava o "login na loja" fora do ar
    // para a nuvem de produção, e parecia ter entrado na loja.
    final principal = ApiClient(baseUrl: baseInicial, client: cliente);
    final login = LoginPelaNuvem(
      principal: principal,
      ipServerNuvem: nuvem,
      httpClient: cliente,
      lerIpServerLocal: () => ipGuardado,
      salvarIpServerLocal: (ip) async => ipGuardado = ip,
    );
    final sessao = await login.entrar(usuario: 'maria', senha: 'x');
    return (sessao, principal);
  }

  setUp(() {
    chamadas = [];
    ipGuardado = null;
    foraDoAr = {};
    ipDaConfig = loja;
    nuvemDaConfig = '';
  });

  // Sem IP local, tudo vai direto para a nuvem — a do `API_URL` do .env da
  // nuvem (`ip_server_nuvem` em /pdv/config/), quando ela informa uma.
  test('sem IP local usa o IP server nuvem informado pela nuvem', () async {
    ipDaConfig = '';
    nuvemDaConfig = 'https://outra.nuvem.test/api/v1';

    final (sessao, principal) = await entrar();

    expect(sessao['access'], 'token-nuvem');
    expect(principal.baseUrl, 'https://outra.nuvem.test/api/v1');
  });

  test(
    'entra na nuvem, pega o IP do server local e passa a usar a loja',
    () async {
      final (sessao, principal) = await entrar();

      expect(sessao['access'], 'token-loja');
      expect(principal.baseUrl, loja);
      expect(ipGuardado, loja);
      expect(chamadas, [
        '$nuvem/auth/login/',
        'https://nuvem.test/api/v1/pdv/config/',
        'http://192.168.0.10/api/v1/auth/login/',
      ]);
    },
  );

  test('loja fora do ar: fica na nuvem, com a sessao da nuvem', () async {
    foraDoAr = {'http://192.168.0.10'};

    final (sessao, principal) = await entrar();

    expect(sessao['access'], 'token-nuvem');
    expect(principal.baseUrl, nuvem);
    expect(ipGuardado, loja, reason: 'o IP vale para a proxima vez');
  });

  test('nuvem fora do ar: entra direto no server local guardado', () async {
    foraDoAr = {'https://nuvem.test'};
    ipGuardado = loja;

    final (sessao, principal) = await entrar(baseInicial: loja);

    expect(sessao['access'], 'token-loja');
    expect(principal.baseUrl, loja);
  });

  test(
    'restaurante sem server local: usa so a nuvem e esquece o IP antigo',
    () async {
      ipDaConfig = '';
      ipGuardado = 'http://10.0.0.1/api/v1';

      final (sessao, principal) = await entrar(baseInicial: ipGuardado!);

      expect(sessao['access'], 'token-nuvem');
      expect(principal.baseUrl, nuvem);
      expect(ipGuardado, isNull);
    },
  );

  test('nuvem fora e nenhum IP guardado: o erro de conexao aparece', () async {
    foraDoAr = {'https://nuvem.test'};

    expect(entrar(), throwsA(isA<Exception>()));
  });
}
