import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/orders/data/conflito_da_venda.dart';

/// A recusa que diz ONDE está o que o caixa procura vira ação, não erro.
///
/// "A comanda 15 já está na conta #42" e "nada a cobrar" deixavam o caixa
/// procurando a conta na lista com o cliente esperando.
void main() {
  ApiException recusa(String codigo, Map<String, dynamic> dados) =>
      ApiException('recusado', statusCode: 409, code: codigo, data: dados);

  test('comanda em outra conta aberta: abre a conta', () {
    final c = ConflitoDaVenda.decidir(
      recusa('comanda_em_outra_conta', {'order_id': 'p42', 'sequence': 42}),
      temLinhasNovas: true,
    );
    expect(c.acao, AcaoDoConflito.abrirConta);
    expect((c.pedidoId, c.numero), ('p42', 42));
  });

  test('comanda ja paga e so ela no rascunho: abre o pedido pago', () {
    final c = ConflitoDaVenda.decidir(
      recusa('comanda_ja_cobrada', {'order_id': 'p42', 'sequence': 42}),
      temLinhasNovas: false,
    );
    expect(c.acao, AcaoDoConflito.abrirPago);
  });

  test(
    'comanda ja paga com itens novos: tira a comanda e nao perde os itens',
    () {
      final c = ConflitoDaVenda.decidir(
        recusa('pedido_ja_pago', {'order_id': 'p42', 'sequence': 42}),
        temLinhasNovas: true,
      );
      expect(c.acao, AcaoDoConflito.tirarComandaPaga);
    },
  );

  test('total mudou: recalcula e diz onde o resto foi cobrado', () {
    final c = ConflitoDaVenda.decidir(
      recusa('total_mudou', {
        'cobradas_em': [
          {'order_id': 'p42', 'sequence': 42},
        ],
      }),
      temLinhasNovas: false,
    );
    expect(c.acao, AcaoDoConflito.recalcular);
    expect(c.ondeCobrou, ['#42']);
  });

  test('recusa sem codigo, ou sem destino, continua sendo erro', () {
    expect(
      ConflitoDaVenda.decidir(
        const ApiException('x'),
        temLinhasNovas: false,
      ).acao,
      AcaoDoConflito.nenhuma,
    );
    expect(
      ConflitoDaVenda.decidir(
        recusa('comanda_ja_cobrada', {}),
        temLinhasNovas: false,
      ).acao,
      AcaoDoConflito.nenhuma,
    );
  });

  test('o cliente le o codigo e o destino do envelope da API', () async {
    final api = ApiClient(
      baseUrl: 'http://loja.test/api/v1',
      client: MockClient(
        (_) async => http.Response(
          '{"success": false, "status_code": 409, "error": {"code": '
          '"comanda_ja_cobrada", "message": "Ja paga", "order_id": "p42", '
          '"sequence": 42}}',
          409,
        ),
      ),
    );

    final erro = await api
        .post(
          '/orders/p1/attach-commands/',
          body: const {},
          accessToken: 'x.eyJ1IjoxfQ.y',
        )
        .then<Object?>((_) => null, onError: (Object e) => e);

    expect(erro, isA<ApiException>());
    final recusada = erro! as ApiException;
    expect(recusada.code, 'comanda_ja_cobrada');
    expect(recusada.data['order_id'], 'p42');
    expect(recusada.message, 'Ja paga');
    await api.dispose();
  });
}
