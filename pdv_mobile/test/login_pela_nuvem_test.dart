import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/features/auth/data/login_pela_nuvem.dart';

/// No login, o app do garçom pega na NUVEM o IP do server local.
///
/// O IP era digitado em cada celular, e mudar o servidor da loja era refazer
/// isso aparelho por aparelho. Agora o login passa pela nuvem (fixa), lê
/// `/pdv/config/` e entra na loja com o mesmo usuário e senha.
void main() {
  const nuvem = 'https://nuvem.test/api/v1';
  const loja = 'http://192.168.0.10/api/v1';

  late List<String> chamadas;
  late String atual;
  late Set<String> foraDoAr;
  late String ipDaConfig;

  http.Client servidores() => MockClient((request) async {
    final base = '${request.url.scheme}://${request.url.authority}';
    chamadas.add('$base${request.url.path}');
    if (foraDoAr.contains(base)) {
      throw http.ClientException('Connection refused', request.url);
    }
    if (request.url.path.endsWith('/pdv/config/')) {
      return http.Response(
        jsonEncode({'restaurant': 'r1', 'ip_server_local': ipDaConfig}),
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
}
