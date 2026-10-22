import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/config/app_config.dart';

/// O endereço com que o PDV ABRE, antes de qualquer login.
///
/// Em "só nuvem" a preferência não devolve o IP da loja, e a abertura caía no
/// `.env` achado na pasta — em desenvolvimento, 127.0.0.1. Quem abria o PDV já
/// logado (sessão guardada) ficava na tela "Dados offline ainda não
/// disponíveis", e "Tentar novamente" batia no mesmo endereço: só sair e
/// entrar, que aponta o cliente para a nuvem, destravava.
void main() {
  test('em só nuvem, o PDV já abre na nuvem', () {
    expect(
      AppConfig.enderecoDeAbertura(somenteNuvem: true, ipDaLoja: null),
      AppConfig.ipServerNuvem,
    );
    expect(
      AppConfig.enderecoDeAbertura(
        somenteNuvem: true,
        ipDaLoja: 'http://172.16.254.51/api/v1',
      ),
      AppConfig.ipServerNuvem,
    );
  });

  test('fora de só nuvem, vale o IP da loja guardado', () {
    expect(
      AppConfig.enderecoDeAbertura(
        somenteNuvem: false,
        ipDaLoja: 'http://172.16.254.51/api/v1',
      ),
      'http://172.16.254.51/api/v1',
    );
    expect(
      AppConfig.enderecoDeAbertura(somenteNuvem: false, ipDaLoja: null),
      isNull,
    );
  });
}
