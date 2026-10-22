import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/response_cache.dart';
import 'package:starchef_pdv_desktop/features/home/data/pdv_catalog.dart';

/// O catálogo não é relido a cada recarga da tela.
///
/// Com 10 s de validade e a tela recarregando a cada aviso da loja, o caixa
/// relia o cardápio inteiro o tempo todo (316 leituras de produtos em 50 min,
/// 13 s cada): o servidor da loja engasgava e o PDV "travava".
void main() {
  test('lista guardada há 30 s, sem aviso, não é relida', () {
    expect(listaDoCatalogoPrecisaReler(const Duration(seconds: 30)), isFalse);
  });

  test('lista marcada como velha por um aviso é relida na hora', () {
    expect(listaDoCatalogoPrecisaReler(ResponseCache.idadeDaVelha), isTrue);
  });

  test('sem cópia, ou passada da rede de segurança, é relida', () {
    expect(listaDoCatalogoPrecisaReler(null), isTrue);
    expect(listaDoCatalogoPrecisaReler(const Duration(minutes: 6)), isTrue);
  });
}
