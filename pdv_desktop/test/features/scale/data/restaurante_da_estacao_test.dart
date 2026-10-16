import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/scale/data/lista_da_estacao.dart';
import 'package:starchef_pdv_desktop/features/scale/data/restaurante_da_estacao.dart';

void main() {
  const restaurantes = [
    {'id': 'r1'},
    {'id': 'r2'},
  ];
  final listas = ListaDaEstacao(
    ApiClient(
      baseUrl: 'http://loja.local/api/v1',
      client: MockClient((_) async => http.Response('{"detail":"x"}', 503)),
    ),
    accessToken: 't',
  );

  test('o já escolhido nesta janela vence o resto', () async {
    expect(
      await restauranteDaEstacao(
        listas: listas,
        restaurantes: restaurantes,
        userId: 'u',
        atual: 'r2',
        pedido: 'r1',
      ),
      'r2',
    );
  });

  test('sem caixa (servidor fora), vale o pedido por quem abriu', () async {
    expect(
      await restauranteDaEstacao(
        listas: listas,
        restaurantes: restaurantes,
        userId: 'u',
        pedido: 'r2',
        doUsuario: 'r1',
      ),
      'r2',
    );
  });

  test('restaurante que não está disponível cai no primeiro', () async {
    expect(
      await restauranteDaEstacao(
        listas: listas,
        restaurantes: restaurantes,
        userId: 'u',
        atual: 'sumiu',
      ),
      'r1',
    );
  });
}
