import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/cloud_fallback.dart';

/// No desvio, a nuvem recebe o token DELA, e o renova nela mesma.
///
/// O token da loja é assinado com outra SECRET_KEY: mandado à nuvem, toda
/// tela respondia "credenciais inválidas" com o garçom logado.
void main() {
  test('desvio usa o token da nuvem e renova na nuvem quando expira', () async {
    final tokens = <String>[];
    var renovou = false;
    final cliente = MockClient((request) async {
      if (request.url.host == 'loja.test') {
        throw http.ClientException('Connection refused', request.url);
      }
      if (request.url.path.endsWith('/auth/refresh/')) {
        renovou = true;
        return http.Response(jsonEncode({'access': 'nuvem-nova'}), 200);
      }
      final token = request.headers['authorization'] ?? '';
      tokens.add(token);
      if (token == 'Bearer nuvem-velha') {
        return http.Response(jsonEncode({'detail': 'Token expirado'}), 401);
      }
      return http.Response(jsonEncode({'results': []}), 200);
    });
    final api = ApiClient(
      baseUrlProvider: () => 'http://loja.test/api/v1',
      httpClient: cliente,
      cloudFallback: CloudFallback(
        baseUrl: 'https://nuvem.test/api/v1',
        intervaloEntreSondas: Duration.zero,
      ),
    );
    final salvos = <String>[];
    api.configureSession(
      accessToken: 'loja',
      refreshToken: 'r-loja',
      terminalId: 't1',
      cloudAccessToken: 'nuvem-velha',
      cloudRefreshToken: 'r-nuvem',
      onCloudTokensChanged: (access, _) async => salvos.add(access),
    );

    await api.get('/commands/');

    expect(tokens, ['Bearer nuvem-velha', 'Bearer nuvem-nova']);
    expect(tokens, isNot(contains('Bearer loja')));
    expect(renovou, isTrue);
    expect(salvos, ['nuvem-nova']);
  });
}
