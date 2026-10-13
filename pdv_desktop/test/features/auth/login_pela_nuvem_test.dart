import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/auth/data/login_pela_nuvem.dart';

/// No login, o PDV pega na NUVEM o IP do server local do restaurante.
///
/// São dois logins: o da nuvem só busca a config (`/pdv/config/`) e é
/// descartado; o que vale é o do server local. Antes a nuvem era a porta de
/// entrada: um usuário que ela não conhecia (a nuvem de produção, num PDV de
/// teste) não entrava nem com a loja respondendo.
void main() {
  const nuvem = 'https://nuvem.test/api/v1';
  const loja = 'http://192.168.0.10/api/v1';

  late List<String> chamadas;
  late String? ipGuardado;
  late Set<String> foraDoAr;
  late String ipDaConfig;
  late String nuvemDaConfig;
  late Set<String> recusamLogin;
  late bool configQuebrada;

  http.Client servidores() => MockClient((request) async {
    final base = '${request.url.scheme}://${request.url.authority}';
    chamadas.add('$base${request.url.path}');
    if (foraDoAr.contains(base)) {
      throw http.ClientException('Connection refused', request.url);
    }
    if (request.url.path.endsWith('/auth/login/') &&
        recusamLogin.contains(base)) {
      return http.Response(
        jsonEncode({'detail': 'No active account found'}),
        401,
      );
    }
    if (request.url.path.endsWith('/pdv/config/')) {
      if (configQuebrada) return http.Response('{}', 500);
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
    bool somenteNuvem = false,
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
      somenteNuvem: () => somenteNuvem,
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
    recusamLogin = {};
    configQuebrada = false;
  });

  test('nuvem recusando o login: entra no server local guardado', () async {
    recusamLogin = {'https://nuvem.test'};
    ipGuardado = loja;

    final (sessao, principal) = await entrar(baseInicial: loja);

    expect(sessao['access'], 'token-loja');
    expect(principal.baseUrl, loja);
    expect(ipGuardado, loja, reason: 'sem config, o padrao fica');
  });

  test('config da nuvem com erro: mantem o IP guardado', () async {
    configQuebrada = true;
    ipGuardado = 'http://10.0.0.1/api/v1';

    final (sessao, principal) = await entrar(baseInicial: ipGuardado!);

    expect(sessao['access'], 'token-loja');
    expect(principal.baseUrl, 'http://10.0.0.1/api/v1');
    expect(ipGuardado, 'http://10.0.0.1/api/v1');
  });

  test('server local recusando a senha: o erro aparece', () async {
    recusamLogin = {'http://192.168.0.10'};

    expect(entrar(), throwsA(isA<ApiException>()));
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

  test('guarda as DUAS sessoes: a da loja e a da nuvem', () async {
    // A da nuvem era descartada, e o desvio mandava o token da loja à
    // nuvem: "credenciais inválidas" em toda tela com o caixa logado.
    final (sessao, _) = await entrar(baseInicial: loja);

    expect(sessao['access'], 'token-loja');
    expect(sessao['cloud_access'], 'token-nuvem');
  });

  test(
    'terminal em so nuvem ignora o IP local da config e fica na nuvem',
    () async {
      // A config da nuvem trazia o IP da loja e forçava o terminal para ela,
      // mesmo com o servidor da loja fora de uso.
      final (sessao, principal) = await entrar(somenteNuvem: true);

      expect(sessao['access'], 'token-nuvem');
      expect(principal.baseUrl, nuvem);
    },
  );
}
