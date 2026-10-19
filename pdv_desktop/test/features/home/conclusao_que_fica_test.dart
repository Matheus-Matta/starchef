import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/errors/error_center.dart';
import 'package:starchef_pdv_desktop/core/input/pdv_shortcuts.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/conclusao_em_andamento.dart';

/// O "Concluir" com o caixa de verdade: a falha que some e a tecla no meio.
void main() {
  testWidgets('a falha da venda fica na tela até o operador fechar', (
    tester,
  ) async {
    // O alerta sumia em 2 s. O caixa virava para entregar a maquininha,
    // voltava, e não havia mensagem nenhuma: "o pedido não finalizou por
    // algum motivo".
    await tester.pumpWidget(const SizedBox());
    final center = ErrorCenter();

    final alerta = center.reportApi(
      const ApiException('O servidor demorou mais de 20 segundos.'),
      title: 'Não foi possível concluir a venda',
      autoDismissAfter: ErrorCenter.ficaAteFechar,
    );
    await tester.pump(const Duration(minutes: 1));

    expect(center.visible, [alerta]);
    center.dismiss(alerta);
    expect(center.visible, isEmpty);
  });

  testWidgets('os outros alertas continuam sumindo sozinhos', (tester) async {
    await tester.pumpWidget(const SizedBox());
    final center = ErrorCenter();

    center.reportApi(const ApiException('Sem rede.'));
    await tester.pump(ErrorCenter.defaultAutoDismissAfter);
    await tester.pump(const Duration(milliseconds: 1));

    expect(center.visible, isEmpty);
  });

  test('durante a conclusão, só a ajuda responde no teclado', () {
    // Esc, F3 ou Ctrl+N no meio do Concluir voltavam a tela e começavam outra
    // venda; a resposta chegava depois e apagava o carrinho do cliente
    // seguinte.
    for (final atalho in PdvShortcuts.all) {
      expect(
        atalhoValeDuranteAConclusao(atalho.id),
        atalho.id == PdvAction.help,
        reason: atalho.id,
      );
    }
  });
}
