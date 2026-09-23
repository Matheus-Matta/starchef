import '../../../core/formatters/value_formatters.dart';

/// Como a impressora está ligada a este terminal.
enum PrinterConnection {
  /// Fila de impressão do sistema operacional, pelo nome da impressora.
  spool,

  /// TCP/IP bruto, normalmente porta 9100.
  network,

  /// Porta serial (COM no Windows, `/dev/tty*` no Linux).
  serial,
}

/// A gaveta de dinheiro ligada à saída RJ12 desta impressora.
///
/// É cadastro do equipamento, não do terminal: quem tem o cabo da gaveta
/// plugado é a impressora, e ela pode ser a mesma para dois PDVs.
class CashDrawerSettings {
  const CashDrawerSettings({
    required this.enabled,
    required this.pin,
    required this.onMs,
    required this.offMs,
  });

  /// Gaveta não cadastrada: nenhum pulso sai em trabalho nenhum.
  static const disabled = CashDrawerSettings(
    enabled: false,
    pin: 2,
    onMs: 100,
    offMs: 400,
  );

  final bool enabled;

  /// Pino do conector (2 na primeira gaveta, 5 na segunda).
  final int pin;

  final int onMs;
  final int offMs;

  factory CashDrawerSettings.fromJson(Map<String, dynamic> printer) {
    final settings = printer['settings'] as Map<String, dynamic>? ?? const {};
    Object? pick(String key) => printer[key] ?? settings[key];
    final pin = ValueFormatters.integer(pick('cash_drawer_pin'), fallback: 2);
    return CashDrawerSettings(
      enabled: pick('cash_drawer_enabled') == true,
      // Só existem duas saídas no comando; qualquer outro número cai na
      // primeira, que é onde uma gaveta única está ligada.
      pin: pin == 5 ? 5 : 2,
      onMs: ValueFormatters.integer(
        pick('cash_drawer_on_ms'),
        fallback: 100,
      ).clamp(1, 510),
      offMs: ValueFormatters.integer(
        pick('cash_drawer_off_ms'),
        fallback: 400,
      ).clamp(1, 510),
    );
  }
}

/// Configuração de transporte de uma impressora, resolvida em um só lugar.
///
/// O cadastro no backend guarda os mesmos campos em dois níveis — direto no
/// objeto e dentro de `settings` —, e o valor pode estar em qualquer um deles.
/// Antes, cada tela e o agente de impressão repetiam essa resolução com regras
/// levemente diferentes; divergências aí significavam uma tela dizendo
/// "impressora configurada" enquanto o agente falhava por endereço ausente.
class PrinterEndpoint {
  const PrinterEndpoint({
    required this.connection,
    required this.endpoint,
    required this.host,
    required this.port,
    required this.baudRate,
    required this.driverType,
    required this.timeout,
    this.cashDrawer = CashDrawerSettings.disabled,
  });

  final PrinterConnection connection;

  /// Nome na fila do sistema (spool) ou caminho da porta serial.
  final String endpoint;

  final String host;
  final int port;
  final int baudRate;
  final String driverType;
  final Duration timeout;
  final CashDrawerSettings cashDrawer;

  factory PrinterEndpoint.fromJson(Map<String, dynamic> printer) {
    final settings = printer['settings'] as Map<String, dynamic>? ?? const {};

    Object? pick(String key) => printer[key] ?? settings[key];

    final rawType = '${settings['connection_type'] ?? printer['connection_type'] ?? 'windows'}'
        .trim()
        .toLowerCase();
    return PrinterEndpoint(
      connection: switch (rawType) {
        'network' => PrinterConnection.network,
        'serial' => PrinterConnection.serial,
        _ => PrinterConnection.spool,
      },
      endpoint: '${printer['endpoint'] ?? ''}'.trim(),
      host: '${pick('host') ?? ''}'.trim(),
      port: ValueFormatters.integer(pick('port'), fallback: 9100),
      baudRate: ValueFormatters.integer(settings['baudrate'], fallback: 9600),
      driverType: '${pick('driver_type') ?? ''}'.trim().toLowerCase(),
      timeout: Duration(
        seconds: ValueFormatters.integer(
          pick('timeout_seconds'),
          fallback: 10,
        ).clamp(1, 120),
      ),
      cashDrawer: CashDrawerSettings.fromJson(printer),
    );
  }

  /// A impressora usa comandos ESC/POS (necessário para código de barras real).
  bool get isEscPos => driverType == 'escpos';

  /// Esta impressora pode abrir uma gaveta?
  ///
  /// O pulso é um comando de controle. Numa impressora que vai pelo driver
  /// gráfico do sistema, os mesmos bytes não são comando nenhum — sairiam
  /// impressos no papel. O cadastro já recusa a combinação, mas o terminal
  /// não depende disso: ele também imprime a partir da cópia guardada na
  /// fila local, gravada por uma versão anterior do backend.
  bool get canOpenCashDrawer => isEscPos && cashDrawer.enabled;

  /// Há endereço suficiente para tentar imprimir.
  bool get isAddressable => switch (connection) {
    PrinterConnection.network => host.isNotEmpty,
    PrinterConnection.serial || PrinterConnection.spool => endpoint.isNotEmpty,
  };

  /// Motivo da configuração incompleta, ou `null` quando está utilizável.
  String? get missingConfiguration {
    if (isAddressable) return null;
    return switch (connection) {
      PrinterConnection.network =>
        'O endereço IP da impressora não foi configurado.',
      PrinterConnection.serial =>
        'A porta serial da impressora não foi configurada.',
      PrinterConnection.spool =>
        'O nome da impressora no sistema não foi configurado.',
    };
  }

  /// Rótulo curto para listas e seletores.
  String get label => switch (connection) {
    PrinterConnection.network => host.isEmpty ? 'Rede' : '$host:$port',
    PrinterConnection.serial =>
      endpoint.isEmpty ? 'Serial' : '$endpoint · $baudRate baud',
    PrinterConnection.spool =>
      endpoint.isEmpty ? 'Sistema / USB' : endpoint,
  };

  /// Rótulo com o tipo de ligação explícito, para telas de cadastro.
  String get describe => switch (connection) {
    PrinterConnection.network => 'Rede · ${host.isEmpty ? '—' : '$host:$port'}',
    PrinterConnection.serial => 'Serial · ${endpoint.isEmpty ? '—' : endpoint}',
    PrinterConnection.spool =>
      'Sistema · ${endpoint.isEmpty ? '—' : endpoint}',
  };
}
