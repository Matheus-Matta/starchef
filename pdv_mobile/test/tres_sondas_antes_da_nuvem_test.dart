import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/cloud_fallback.dart';

/// A loja só é dada como FORA depois de três sondas seguidas sem resposta.
///
/// Com uma sonda só, o serviço da loja reiniciando ou a rede do salão
/// piscando trocava o aparelho para a nuvem em segundos — e trocar de
/// servidor no meio do atendimento é pior que esperar um pouco.
void main() {
  CloudFallback fallback() =>
      CloudFallback(intervaloEntreSondas: Duration.zero);

  test('uma falha isolada nao troca de servidor', () async {
    var sondas = 0;
    final respostas = [false, true];
    final fora = await fallback().confirmarQuedaDoLocal(
      () async => respostas[sondas++],
    );
    expect(fora, isFalse);
    expect(sondas, 2);
  });

  test('tres falhas seguidas trocam para a nuvem', () async {
    var sondas = 0;
    final alvo = fallback();
    final fora = await alvo.confirmarQuedaDoLocal(() async {
      sondas++;
      return false;
    });
    expect(fora, isTrue);
    expect(sondas, 3);
    expect(alvo.localForaDoAr, isTrue);
  });

  test('o padrao espera entre as sondas', () {
    final padrao = CloudFallback();
    expect(padrao.sondasAntesDeDesviar, 3);
    expect(padrao.intervaloEntreSondas, const Duration(seconds: 2));
  });
}
