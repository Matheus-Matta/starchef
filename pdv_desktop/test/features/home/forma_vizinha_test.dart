import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/home/data/forma_vizinha.dart';

/// ↑ e ↓ andam na lista de formas de pagamento, dando a volta nas pontas.
void main() {
  final formas = [
    {'id': 'pix'},
    {'id': 'debito'},
    {'id': 'dinheiro'},
  ];

  test('desce e sobe uma posicao', () {
    expect(formaVizinha(formas, 'pix', 1), 'debito');
    expect(formaVizinha(formas, 'dinheiro', -1), 'debito');
  });

  test('nas pontas da a volta', () {
    expect(formaVizinha(formas, 'dinheiro', 1), 'pix');
    expect(formaVizinha(formas, 'pix', -1), 'dinheiro');
  });

  test('sem selecao comeca pela primeira; sem formas, nada', () {
    expect(formaVizinha(formas, null, 1), 'pix');
    expect(formaVizinha(formas, 'sumiu', 1), 'pix');
    expect(formaVizinha(const [], 'pix', 1), isNull);
  });
}
