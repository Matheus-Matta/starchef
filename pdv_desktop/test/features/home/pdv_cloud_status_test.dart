import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/printer.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_operational_chrome.dart';

/// Quando a loja cai e quem atende é a nuvem, o operador vê isso no selo da
/// barra — sem faixa atravessada na tela. O selo que dizia "Nuvem não
/// monitorada" passa a dizer "Conectado à nuvem", e o do servidor local deixa
/// de dizer "Servidor local", que seria mentira.
void main() {
  Future<void> montar(
    WidgetTester tester, {
    required NetworkPhase fase,
    bool syncPending = false,
  }) async {
    final printer = ValueNotifier(PrinterAvailability.disconnected);
    addTearDown(printer.dispose);
    addTearDown(tester.view.reset);
    tester.view.physicalSize = const Size(1366, 768);
    tester.view.devicePixelRatio = 1;
    await tester.pumpWidget(
      MaterialApp(
        home: Align(
          alignment: Alignment.topCenter,
          child: PdvOperationalBar(
            cashName: 'Caixa 01',
            operatorName: 'Operador',
            shiftLabel: 'Turno',
            cashOpen: true,
            network: NetworkStatus(phase: fase),
            printer: printer,
            syncPending: syncPending,
          ),
        ),
      ),
    );
  }

  testWidgets('servido pela nuvem o selo diz Conectado a nuvem', (
    tester,
  ) async {
    await montar(tester, fase: NetworkPhase.cloud);

    expect(find.text('Conectado à nuvem'), findsOneWidget);
    expect(find.text('Nuvem não monitorada'), findsNothing);
    expect(find.text('Servidor local'), findsNothing);
    expect(find.text('Sem servidor local'), findsOneWidget);
  });

  testWidgets('no caminho normal o selo segue Nuvem nao monitorada', (
    tester,
  ) async {
    await montar(tester, fase: NetworkPhase.online);

    expect(find.text('Nuvem não monitorada'), findsOneWidget);
    expect(find.text('Conectado à nuvem'), findsNothing);
    expect(find.text('Servidor local'), findsOneWidget);
  });

  testWidgets('a venda pendente de envio continua aparecendo', (tester) async {
    await montar(tester, fase: NetworkPhase.online, syncPending: true);

    expect(find.text('Sincronização pendente'), findsOneWidget);
  });

  group('o estado de rede', () {
    test('a fase da nuvem CONTA como ter conexao', () {
      // Quem atende é a nuvem, mas há conexão: marcar como offline faria a
      // tela recusar gestos que estão funcionando.
      const status = NetworkStatus(phase: NetworkPhase.cloud);

      expect(status.hasConnection, isTrue);
      expect(status.servidoPelaNuvem, isTrue);
    });

    test('o caminho normal NAO e servido pela nuvem', () {
      const status = NetworkStatus(phase: NetworkPhase.online);

      expect(status.servidoPelaNuvem, isFalse);
    });
  });
}
