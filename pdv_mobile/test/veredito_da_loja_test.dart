import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/cloud_fallback.dart';
import 'package:starchef_pdv_mobile/core/network/veredito_da_loja.dart';

/// Caiu para a nuvem, FICA na nuvem por 5 minutos — e só volta depois de um
/// ping confirmar que a loja está de pé.
///
/// A janela começava em 30 s e qualquer resposta da loja a desfazia (fechar
/// comanda tentava a loja primeiro): o terminal pulava de servidor no meio de
/// uma venda, e metade dela ia para cada lado.
void main() {
  late DateTime agora;
  late VereditoDaLoja veredito;
  late CloudFallback fallback;

  setUp(() {
    agora = DateTime(2026, 10, 10, 12);
    veredito = VereditoDaLoja(relogio: () => agora);
    fallback = CloudFallback(veredito: veredito);
  });

  void passa(Duration tempo) => agora = agora.add(tempo);

  test('fica na nuvem 5 minutos, mesmo que a loja responda no meio', () {
    veredito.marcarForaDoAr();
    passa(const Duration(minutes: 4, seconds: 59));
    veredito.localRespondeu(); // ex.: a nota fiscal, que nunca desvia
    expect(veredito.localForaDoAr, isTrue);
    expect(veredito.precisaConferir, isFalse);
  });

  test('vencidos os 5 minutos, o ping decide: loja de pe volta', () async {
    veredito.marcarForaDoAr();
    passa(VereditoDaLoja.janela);
    expect(veredito.precisaConferir, isTrue);

    await fallback.conferirSeVenceu(() async => true);

    expect(veredito.localForaDoAr, isFalse);
  });

  test(
    'vencidos os 5 minutos, loja ainda fora: mais 5 minutos na nuvem',
    () async {
      veredito.marcarForaDoAr();
      passa(VereditoDaLoja.janela);

      await fallback.conferirSeVenceu(() async => false);

      expect(veredito.localForaDoAr, isTrue);
      expect(veredito.precisaConferir, isFalse);
      passa(VereditoDaLoja.janela);
      expect(veredito.precisaConferir, isTrue);
    },
  );

  test('dentro da janela nao gasta ping', () async {
    var pings = 0;
    veredito.marcarForaDoAr();
    passa(const Duration(minutes: 2));
    await fallback.conferirSeVenceu(() async {
      pings++;
      return true;
    });
    expect(pings, 0);
    expect(veredito.localForaDoAr, isTrue);
  });

  group('com a loja fora, vai direto para a nuvem', () {
    test('leitura, escrita e fechar comanda vao direto', () {
      veredito.marcarForaDoAr();
      expect(fallback.irDiretoParaANuvem('/orders/'), isTrue);
      expect(fallback.irDiretoParaANuvem('/commands/'), isTrue);
      // O restaurante inteiro está de um lado: fechar a comanda na loja no
      // meio da janela era o que espalhava a venda pelos dois servidores.
      expect(
        fallback.irDiretoParaANuvem('/orders/p1/attach-commands/'),
        isTrue,
      );
    });

    test('fiscal e caixa continuam na loja', () {
      veredito.marcarForaDoAr();
      expect(fallback.irDiretoParaANuvem('/invoices/1/emit/'), isFalse);
      expect(fallback.irDiretoParaANuvem('/cash-register/open/'), isFalse);
    });

    test('loja de pe ou desvio desligado nao desviam', () {
      expect(fallback.irDiretoParaANuvem('/orders/'), isFalse);
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
