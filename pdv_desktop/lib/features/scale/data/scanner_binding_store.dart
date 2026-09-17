import 'dart:convert';
import 'dart:io';

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

  Map<String, dynamic> toJson() => {
    'slot': slot,
    'port_name': portName,
    'baud_rate': baudRate,
    'vendor_id': vendorId,
    'product_id': productId,
    'serial_number': serialNumber,
    'product_name': productName,
  };

  static ScannerBinding fromJson(Map<String, dynamic> row) => ScannerBinding(
    slot: '${row['slot']}',
    portName: '${row['port_name']}',
    baudRate: (row['baud_rate'] as num?)?.toInt() ?? 9600,
    vendorId: (row['vendor_id'] as num?)?.toInt(),
    productId: (row['product_id'] as num?)?.toInt(),
    serialNumber: row['serial_number']?.toString(),
    productName: row['product_name']?.toString(),
  );

  static String _hex(int value) =>
      '0x${value.toRadixString(16).padLeft(4, '0').toUpperCase()}';
}

/// A porta serial pedida já é de outro slot.
///
/// Dois slots na mesma porta disputariam as mesmas leituras, e o mesmo código
/// de barras chegaria a duas telas.
class ScannerPortAlreadyBound implements Exception {
  const ScannerPortAlreadyBound({
    required this.portName,
    required this.boundSlot,
  });

  final String portName;
  final String boundSlot;

  @override
  String toString() =>
      'A porta $portName já está vinculada a $boundSlot.';
}

/// Qual leitor está em qual porta desta máquina.
///
/// É informação de hardware, não de negócio: ela descreve o equipamento
/// plugado nesta mesa e não existe no servidor. Por isso continua em disco
/// mesmo num PDV que só opera conectado — sem ela, o operador teria que
/// reapontar o leitor a cada abertura.
class ScannerBindingStore {
  ScannerBindingStore({File? file}) : _file = file ?? _defaultFile();

  final File _file;
  Map<String, ScannerBinding>? _cache;
  Future<void> _writeTail = Future.value();

  static File _defaultFile() => AppPaths.dataFile('device_bindings.json');

  Future<Map<String, ScannerBinding>> _load() async {
    final cached = _cache;
    if (cached != null) return cached;
    final bindings = <String, ScannerBinding>{};
    try {
      if (await _file.exists()) {
        final decoded = jsonDecode(await _file.readAsString());
        if (decoded is Map) {
          for (final entry in decoded.entries) {
            if (entry.value is! Map) continue;
            bindings['${entry.key}'] = ScannerBinding.fromJson(
              Map<String, dynamic>.from(entry.value as Map),
            );
          }
        }
      }
    } catch (_) {
      // Arquivo corrompido: o operador reaponta o leitor, que é um gesto de
      // segundos. Impedir a abertura do PDV por causa disso seria pior.
    }
    return _cache = bindings;
  }

  Future<ScannerBinding?> read(String slot) async => (await _load())[slot];

  /// Vincula um leitor a um slot.
  ///
  /// Recusa quando a porta já é de outro slot, e a recusa é o comportamento
  /// que a tela espera: ela vira "este leitor já está vinculado a outra
  /// balança". Reatribuir em silêncio seria pior — o leitor pararia de
  /// alimentar a balança anterior e ninguém saberia por quê.
  Future<void> save(ScannerBinding binding) async {
    final bindings = await _load();
    final conflito = bindings.entries.firstWhere(
      (entry) =>
          entry.key != binding.slot &&
          entry.value.portName == binding.portName,
      orElse: () => const MapEntry('', ScannerBinding(
        slot: '',
        portName: '',
        baudRate: 0,
      )),
    );
    if (conflito.key.isNotEmpty) {
      throw ScannerPortAlreadyBound(
        portName: binding.portName,
        boundSlot: conflito.key,
      );
    }
    bindings[binding.slot] = binding;
    await _flush(bindings);
  }

  Future<void> clear(String slot) async {
    final bindings = await _load();
    if (bindings.remove(slot) == null) return;
    await _flush(bindings);
  }

  Future<void> close() => _writeTail;

  Future<void> _flush(Map<String, ScannerBinding> bindings) {
    final snapshot = {
      for (final entry in bindings.entries) entry.key: entry.value.toJson(),
    };
    // As gravações são encadeadas e atômicas: duas trocas de leitor em
    // sequência não podem produzir um arquivo meio escrito.
    return _writeTail = _writeTail.then((_) async {
      await _file.parent.create(recursive: true);
      final temporary = File('${_file.path}.tmp');
      await temporary.writeAsString(jsonEncode(snapshot), flush: true);
      await temporary.rename(_file.path);
    });
  }
}
