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
  });

  final PrinterConnection connection;

  /// Nome na fila do sistema (spool) ou caminho da porta serial.
  final String endpoint;

  final String host;
  final int port;
  final int baudRate;
  final String driverType;
  final Duration timeout;

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
    );
  }

  /// A impressora usa comandos ESC/POS (necessário para código de barras real).
  bool get isEscPos => driverType == 'escpos';

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
