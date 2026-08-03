import 'dart:io';

import 'package:sqlite_async/sqlite_async.dart';

import '../../../core/storage/app_paths.dart';

class ScannerBinding {
  const ScannerBinding({
    required this.slot,
    required this.portName,
    required this.baudRate,
    this.vendorId,
    this.productId,
    this.serialNumber,
    this.productName,
  });

  final String slot;
  final String portName;
  final int baudRate;
  final int? vendorId;
  final int? productId;
  final String? serialNumber;
  final String? productName;

  String get hardwareIdentity {
    final ids = [
      if (vendorId != null) 'VID ${_hex(vendorId!)}',
      if (productId != null) 'PID ${_hex(productId!)}',
      if (serialNumber?.trim().isNotEmpty == true) 'SN $serialNumber',
    ];
    return ids.isEmpty ? portName : '$portName · ${ids.join(' · ')}';
  }

  static String _hex(int value) =>
      '0x${value.toRadixString(16).padLeft(4, '0').toUpperCase()}';
}

class ScannerBindingStore {
  ScannerBindingStore({File? file}) : _file = file ?? _defaultFile() {
    _database = SqliteDatabase(path: _file.path);
    _ready = _initialize();
  }

  final File _file;
  late final SqliteDatabase _database;
  late final Future<void> _ready;

  static File _defaultFile() {
    return AppPaths.dataFile('device_bindings.sqlite');
  }

  Future<void> _initialize() async {
    await _file.parent.create(recursive: true);
    final migrations = SqliteMigrations()
      ..createDatabase = SqliteMigration(1, _createSchema)
      ..add(SqliteMigration(1, _createSchema));
    await migrations.migrate(_database);
  }

  static Future<void> _createSchema(SqliteWriteContext tx) async {
    await tx.execute('''
      CREATE TABLE IF NOT EXISTS scanner_bindings (
        slot TEXT PRIMARY KEY,
        port_name TEXT NOT NULL UNIQUE,
        baud_rate INTEGER NOT NULL,
        vendor_id INTEGER,
        product_id INTEGER,
        serial_number TEXT,
        product_name TEXT,
        updated_at TEXT NOT NULL
      )
    ''');
  }

  Future<ScannerBinding?> read(String slot) async {
    await _ready;
    final row = await _database.getOptional(
      'SELECT * FROM scanner_bindings WHERE slot = ?',
      [slot],
    );
    if (row == null) return null;
    return ScannerBinding(
      slot: '${row['slot']}',
      portName: '${row['port_name']}',
      baudRate: (row['baud_rate'] as num?)?.toInt() ?? 9600,
      vendorId: (row['vendor_id'] as num?)?.toInt(),
      productId: (row['product_id'] as num?)?.toInt(),
      serialNumber: row['serial_number']?.toString(),
      productName: row['product_name']?.toString(),
    );
  }

  Future<void> save(ScannerBinding binding) async {
    await _ready;
    await _database.execute(
      '''
      INSERT INTO scanner_bindings(
        slot, port_name, baud_rate, vendor_id, product_id, serial_number,
        product_name, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(slot) DO UPDATE SET
        port_name = excluded.port_name,
        baud_rate = excluded.baud_rate,
        vendor_id = excluded.vendor_id,
        product_id = excluded.product_id,
        serial_number = excluded.serial_number,
        product_name = excluded.product_name,
        updated_at = excluded.updated_at
      ''',
      [
        binding.slot,
        binding.portName,
        binding.baudRate,
        binding.vendorId,
        binding.productId,
        binding.serialNumber,
        binding.productName,
        DateTime.now().toUtc().toIso8601String(),
      ],
    );
  }

  Future<void> clear(String slot) async {
    await _ready;
    await _database.execute('DELETE FROM scanner_bindings WHERE slot = ?', [
      slot,
    ]);
  }

  Future<void> close() async {
    await _ready;
    await _database.close();
  }
}
