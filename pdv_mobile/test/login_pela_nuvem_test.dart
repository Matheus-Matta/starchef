import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_exception.dart';
import 'package:starchef_pdv_mobile/features/auth/data/login_pela_nuvem.dart';

/// No login, o app do garçom pega na NUVEM o IP do server local.
///
/// São dois logins: o da nuvem só busca a config (`/pdv/config/`) e é
/// descartado; o que vale é o do server local. Antes a nuvem era a porta de
/// entrada: um garçom que ela não conhecia não entrava nem com a loja
/// respondendo.
void main() {
  const nuvem = 'https://nuvem.test/api/v1';
  const loja = 'http://192.168.0.10/api/v1';

  late List<String> chamadas;
  late String atual;
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

  Future<Map<String, dynamic>> entrar() {
    final cliente = servidores();
    return LoginPelaNuvem(
      ipServerNuvem: nuvem,
      httpClient: cliente,
      lerIpServerLocal: () => atual == nuvem ? null : atual,
      usarServidor: (url) async => atual = url,
    ).entrar(
      usuario: 'joao',
      senha: 'x',
      extras: const {'client': 'waiter_app'},
    );
  }

  setUp(() {
    chamadas = [];
    atual = nuvem;
    foraDoAr = {};
    ipDaConfig = loja;
    nuvemDaConfig = '';
    recusamLogin = {};
    configQuebrada = false;
  });

  test('nuvem recusando o login: entra no server local guardado', () async {
    recusamLogin = {'https://nuvem.test'};
    atual = loja;

    final sessao = await entrar();

    expect(sessao['access'], 'token-loja');
    expect(atual, loja);
  });

  test('config da nuvem com erro: mantem o IP guardado', () async {
    configQuebrada = true;
    atual = 'http://10.0.0.1/api/v1';

    final sessao = await entrar();

    expect(sessao['access'], 'token-loja');
    expect(atual, 'http://10.0.0.1/api/v1');
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

    final sessao = await entrar();

    expect(sessao['access'], 'token-nuvem');
    expect(atual, 'https://outra.nuvem.test/api/v1');
  });

  test(
    'entra na nuvem, pega o IP do server local e passa a usar a loja',
    () async {
      final sessao = await entrar();

      expect(sessao['access'], 'token-loja');
      expect(atual, loja);
      expect(chamadas, [
        '$nuvem/auth/login/',
        '$nuvem/pdv/config/',
        '$loja/auth/login/',
      ]);
    },
  );

  test('loja fora do ar: fica na nuvem', () async {
    foraDoAr = {'http://192.168.0.10'};

    final sessao = await entrar();

    expect(sessao['access'], 'token-nuvem');
    expect(atual, nuvem);
  });

  test('nuvem fora do ar: entra direto no server local guardado', () async {
    foraDoAr = {'https://nuvem.test'};
    atual = loja;

    final sessao = await entrar();

    expect(sessao['access'], 'token-loja');
    expect(atual, loja);
  });

  test('restaurante sem server local: usa so a nuvem', () async {
    ipDaConfig = '';
    atual = 'http://10.0.0.1/api/v1';

    final sessao = await entrar();

    expect(sessao['access'], 'token-nuvem');
    expect(atual, nuvem);
  });

  test('guarda as DUAS sessoes: a da loja e a da nuvem', () async {
    // A da nuvem era descartada, e o desvio mandava o token da loja à
    // nuvem: "credenciais inválidas" em toda tela com o garçom logado.
    final sessao = await entrar();

    expect(sessao['access'], 'token-loja');
    expect(sessao['cloud_access'], 'token-nuvem');
  });

  test('logado na propria nuvem, a sessao da nuvem e a principal', () async {
    ipDaConfig = '';

    final sessao = await entrar();

    expect(sessao['access'], 'token-nuvem');
    expect(sessao['cloud_access'], 'token-nuvem');
  });
}
