class MobilePrinter {
  const MobilePrinter({
    required this.id,
    required this.name,
    required this.host,
    required this.port,
    required this.timeout,
    required this.driver,
    required this.active,
    required this.autoPrint,
  });

  final String id;
  final String name;
  final String host;
  final int port;
  final Duration timeout;
  final String driver;
  final bool active;
  final bool autoPrint;

  bool get isAddressable =>
      active && host.isNotEmpty && port > 0 && port <= 65535;
  bool get supportsMobile => isAddressable;
  bool get acceptsAutomaticJobs => supportsMobile && autoPrint;
  bool get isEscPos => driver == 'escpos';

  factory MobilePrinter.fromJson(Map<String, dynamic> json) {
    final settings = json['settings'] is Map
        ? Map<String, dynamic>.from(json['settings'] as Map)
        : const <String, dynamic>{};
    final connection =
        '${json['connection_type'] ?? settings['connection_type'] ?? ''}';
    final seconds = _integer(
      json['timeout_seconds'] ?? settings['timeout_seconds'],
      fallback: 10,
    );
    return MobilePrinter(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? 'Impressora'}',
      host: connection == 'network'
          ? '${json['host'] ?? settings['host'] ?? ''}'.trim()
          : '',
      port: _integer(json['port'] ?? settings['port'], fallback: 9100),
      timeout: Duration(seconds: seconds.clamp(1, 120)),
      driver: '${json['driver_type'] ?? 'escpos'}',
      active: json['is_active'] != false,
      autoPrint: json['auto_print'] == true,
    );
  }

  static int _integer(Object? value, {required int fallback}) =>
      value is num ? value.toInt() : int.tryParse('$value') ?? fallback;
}
