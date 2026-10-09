import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_desktop/core/network/veredito_da_loja.dart';

/// A loja instável não pode arrastar o terminal de um servidor para o outro.
///
/// Com a janela fixa de 30 s, a loja que reiniciava a cada minuto fazia a tela
/// piscar "loja"/"nuvem" e o mesmo pedido ser editado nos dois servidores.
void main() {
  late DateTime agora;
  late VereditoDaLoja veredito;

  setUp(() {
    agora = DateTime(2026, 10, 8, 12);
    veredito = VereditoDaLoja(relogio: () => agora);
  });

  void passa(Duration tempo) => agora = agora.add(tempo);

  test('a primeira queda segura o terminal na nuvem por 30 segundos', () {
    veredito.marcarForaDoAr();
    passa(const Duration(seconds: 29));
    expect(veredito.localForaDoAr, isTrue);
    passa(const Duration(seconds: 2));
    expect(veredito.localForaDoAr, isFalse);
  });

  test('cair de novo logo depois de voltar dobra a janela, ate 5 minutos', () {
    final janelas = <Duration>[];
    for (var i = 0; i < 6; i++) {
      veredito.marcarForaDoAr();
      janelas.add(veredito.janela);
      passa(veredito.janela + const Duration(seconds: 1));
      expect(veredito.localForaDoAr, isFalse);
      veredito.localRespondeu();
      passa(const Duration(seconds: 20));
    }
    expect(janelas.map((j) => j.inSeconds), [30, 60, 120, 240, 300, 300]);
  });

  test('a loja que fica de pe por 5 minutos zera a contagem', () {
    veredito.marcarForaDoAr();
    passa(const Duration(seconds: 31));
    veredito.localRespondeu();
    passa(const Duration(seconds: 10));
    veredito.marcarForaDoAr();
    expect(veredito.janela, const Duration(minutes: 1));

    passa(const Duration(minutes: 2));
    veredito.localRespondeu();
    passa(VereditoDaLoja.estabilidade + const Duration(seconds: 1));
    veredito.marcarForaDoAr();
    expect(veredito.janela, VereditoDaLoja.janelaBase);
  });

  group('com a loja fora, vai direto para a nuvem', () {
    test('leitura e escrita comuns vao direto', () {
      final fallback = CloudFallback(veredito: veredito);
      veredito.marcarForaDoAr();
      expect(fallback.irDiretoParaANuvem('/orders/'), isTrue);
      expect(fallback.irDiretoParaANuvem('/commands/'), isTrue);
    });

    test('fechar comanda tenta a loja antes (cobranca em dobro)', () {
      final fallback = CloudFallback(veredito: veredito);
      veredito.marcarForaDoAr();
      expect(fallback.irDiretoParaANuvem('/orders/p1/attach-commands/'), isFalse);
    });

    test('fiscal e caixa continuam na loja', () {
      final fallback = CloudFallback(veredito: veredito);
      veredito.marcarForaDoAr();
      expect(fallback.irDiretoParaANuvem('/invoices/1/emit/'), isFalse);
      expect(fallback.irDiretoParaANuvem('/cash-register/open/'), isFalse);
    });

    test('loja de pe ou desvio desligado nao desviam', () {
      expect(
        CloudFallback(veredito: veredito).irDiretoParaANuvem('/orders/'),
        isFalse,
      );
      veredito.marcarForaDoAr();
      expect(
        CloudFallback(
          veredito: veredito,
          enabled: false,
        ).irDiretoParaANuvem('/orders/'),
        isFalse,
      );
    });
  });
}
