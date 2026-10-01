import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/serial_port_release.dart';

void main() {
  // `testWidgets` roda com relógio falso: `pump(duração)` avança o tempo sem
  // esperar de verdade.
  testWidgets(
    'a porta fecha na hora e só é liberada depois da folga do leitor',
    (tester) async {
      // Liberar junto com o fechamento deixava o isolate do leitor lendo
      // memória já liberada — e o Windows fechava a Balança Rápida sem log.
      final passos = <String>[];

      releaseAfterReader(
        close: () => passos.add('close'),
        free: () => passos.add('free'),
      );

      expect(passos, ['close']);
      await tester.pump(serialReaderGrace - const Duration(milliseconds: 1));
      expect(passos, ['close']);
      await tester.pump(const Duration(milliseconds: 1));
      expect(passos, ['close', 'free']);
    },
  );

  testWidgets(
    'uma falha ao fechar não impede a liberação nem sobe para a tela',
    (tester) async {
      var liberada = false;

      releaseAfterReader(
        close: () => throw StateError('cabo removido'),
        free: () => liberada = true,
      );
      await tester.pump(serialReaderGrace);

      expect(liberada, isTrue);
    },
  );
}
