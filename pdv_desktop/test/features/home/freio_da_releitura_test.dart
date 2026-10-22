import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/data/freio_da_releitura.dart';

/// Cada item lançado numa comanda, em qualquer aparelho, fazia todos os PDVs
/// relerem a lista INTEIRA de comandas — uma vez por item.
void main() {
  test('dentro do intervalo não relê, e agenda UMA releitura no fim', () async {
    var agora = DateTime(2026, 10, 22, 12);
    final freio = FreioDaReleitura(
      intervalo: const Duration(milliseconds: 80),
      agora: () => agora,
    );
    addTearDown(freio.dispose);
    var depois = 0;

    expect(freio.podeReler('r/commands/', depois: () => depois++), isTrue);
    // Dez avisos seguidos: nenhuma releitura agora, uma só agendada.
    for (var i = 0; i < 10; i++) {
      expect(freio.podeReler('r/commands/', depois: () => depois++), isFalse);
    }
    expect(freio.temAdiada('r/commands/'), isTrue);

    await Future<void>.delayed(const Duration(milliseconds: 150));
    expect(depois, 1, reason: 'a mudança não se perde: relê no fim');

    agora = agora.add(const Duration(milliseconds: 80));
    expect(freio.podeReler('r/commands/', depois: () => depois++), isTrue);
  });

  test('cada lista tem o seu intervalo', () {
    final freio = FreioDaReleitura();
    addTearDown(freio.dispose);

    expect(freio.podeReler('r/commands/', depois: () {}), isTrue);
    expect(freio.podeReler('r/tables/', depois: () {}), isTrue);
  });
}
