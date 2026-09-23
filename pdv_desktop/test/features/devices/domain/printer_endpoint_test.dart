import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/devices/domain/printer_endpoint.dart';

void main() {
  test('lê a conexão preferindo settings sobre o campo direto', () {
    final target = PrinterEndpoint.fromJson({
      'connection_type': 'windows',
      'settings': {'connection_type': 'network'},
      'host': '192.168.0.50',
    });

    expect(target.connection, PrinterConnection.network);
  });

  test('cai para a fila do sistema quando nada foi informado', () {
    final target = PrinterEndpoint.fromJson({'endpoint': 'Epson TM-T20'});

    expect(target.connection, PrinterConnection.spool);
    expect(target.endpoint, 'Epson TM-T20');
    expect(target.isAddressable, isTrue);
  });

  test('aceita host e porta vindos de qualquer um dos dois níveis', () {
    final direto = PrinterEndpoint.fromJson({
      'connection_type': 'network',
      'host': '10.0.0.5',
      'port': 9101,
    });
    final aninhado = PrinterEndpoint.fromJson({
      'settings': {'connection_type': 'network', 'host': '10.0.0.5', 'port': 9101},
    });

    expect(direto.host, aninhado.host);
    expect(direto.port, aninhado.port);
    expect(direto.label, aninhado.label);
  });

  test('usa 9100 e 9600 como padrões', () {
    final target = PrinterEndpoint.fromJson({
      'connection_type': 'network',
      'host': '10.0.0.5',
    });

    expect(target.port, 9100);
    expect(target.baudRate, 9600);
  });

  group('configuração incompleta', () {
    test('rede sem host não é endereçável', () {
      final target = PrinterEndpoint.fromJson({'connection_type': 'network'});

      expect(target.isAddressable, isFalse);
      expect(target.missingConfiguration, contains('IP'));
    });

    test('serial sem porta não é endereçável', () {
      final target = PrinterEndpoint.fromJson({'connection_type': 'serial'});

      expect(target.isAddressable, isFalse);
      expect(target.missingConfiguration, contains('serial'));
    });

    test('spool sem nome não é endereçável', () {
      final target = PrinterEndpoint.fromJson(const {});

      expect(target.isAddressable, isFalse);
      expect(target.missingConfiguration, isNotNull);
    });

    test('uma impressora completa não reporta pendência', () {
      final target = PrinterEndpoint.fromJson({
        'connection_type': 'serial',
        'endpoint': 'COM4',
        'settings': {'baudrate': 115200},
      });

      expect(target.missingConfiguration, isNull);
      expect(target.baudRate, 115200);
    });
  });

  test('reconhece o driver ESC/POS, que habilita código de barras real', () {
    expect(
      PrinterEndpoint.fromJson({'driver_type': 'ESCPOS'}).isEscPos,
      isTrue,
    );
    expect(
      PrinterEndpoint.fromJson({'driver_type': 'generic'}).isEscPos,
      isFalse,
    );
    expect(PrinterEndpoint.fromJson(const {}).isEscPos, isFalse);
  });

  test('o timeout fica dentro de limites operacionais', () {
    expect(
      PrinterEndpoint.fromJson({'timeout_seconds': 0}).timeout,
      const Duration(seconds: 1),
    );
    expect(
      PrinterEndpoint.fromJson({'timeout_seconds': 999}).timeout,
      const Duration(seconds: 120),
    );
    expect(
      PrinterEndpoint.fromJson(const {}).timeout,
      const Duration(seconds: 10),
    );
  });

  test('os rótulos descrevem o transporte para o operador', () {
    expect(
      PrinterEndpoint.fromJson({
        'connection_type': 'network',
        'host': '10.0.0.5',
        'port': 9100,
      }).label,
      '10.0.0.5:9100',
    );
    expect(
      PrinterEndpoint.fromJson({
        'connection_type': 'serial',
        'endpoint': 'COM3',
      }).label,
      'COM3 · 9600 baud',
    );
    expect(
      PrinterEndpoint.fromJson({'endpoint': 'Balcao'}).describe,
      'Sistema · Balcao',
    );
  });

  group('gaveta de dinheiro', () {
    test('sem cadastro, nenhuma impressora abre gaveta', () {
      final endpoint = PrinterEndpoint.fromJson({
        'connection_type': 'network',
        'host': '10.0.0.5',
        'driver_type': 'escpos',
      });

      expect(endpoint.cashDrawer.enabled, isFalse);
      expect(endpoint.canOpenCashDrawer, isFalse);
    });

    test('lê a gaveta do nível de cima ou de dentro de settings', () {
      // A cópia guardada na fila local vem de um cadastro completo; a tela de
      // equipamentos monta o mapa com os campos que tem na mão. Os dois
      // precisam resolver igual.
      for (final json in [
        const {
          'driver_type': 'escpos',
          'endpoint': 'Caixa',
          'cash_drawer_enabled': true,
          'cash_drawer_pin': 5,
          'cash_drawer_on_ms': 120,
          'cash_drawer_off_ms': 480,
        },
        const {
          'driver_type': 'escpos',
          'endpoint': 'Caixa',
          'settings': {
            'cash_drawer_enabled': true,
            'cash_drawer_pin': 5,
            'cash_drawer_on_ms': 120,
            'cash_drawer_off_ms': 480,
          },
        },
      ]) {
        final drawer = PrinterEndpoint.fromJson(json).cashDrawer;
        expect(drawer.enabled, isTrue);
        expect(drawer.pin, 5);
        expect(drawer.onMs, 120);
        expect(drawer.offMs, 480);
      }
    });

    test('um pino desconhecido cai na primeira saída', () {
      final drawer = PrinterEndpoint.fromJson({
        'driver_type': 'escpos',
        'endpoint': 'Caixa',
        'cash_drawer_enabled': true,
        'cash_drawer_pin': 7,
      }).cashDrawer;

      expect(drawer.pin, 2);
    });

    test('gaveta cadastrada fora do ESC/POS não é acionável', () {
      final endpoint = PrinterEndpoint.fromJson({
        'driver_type': 'browser',
        'endpoint': 'Caixa',
        'cash_drawer_enabled': true,
      });

      expect(endpoint.cashDrawer.enabled, isTrue);
      // No driver gráfico os bytes do pulso sairiam impressos no papel.
      expect(endpoint.canOpenCashDrawer, isFalse);
    });
  });
}
