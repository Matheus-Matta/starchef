import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../../../core/hardware/leitor_serial_isolado.dart';
import '../data/scanner_binding_store.dart';

class SerialScannerDevice {
  const SerialScannerDevice({
    required this.portName,
    this.vendorId,
    this.productId,
    this.serialNumber,
    this.productName,
    this.manufacturer,
  });

  final String portName;
  final int? vendorId;
  final int? productId;
  final String? serialNumber;
  final String? productName;
  final String? manufacturer;

  String get label {
    final name = productName?.trim().isNotEmpty == true
        ? productName!
        : manufacturer?.trim().isNotEmpty == true
        ? manufacturer!
        : 'Scanner serial';
    final ids = [
      if (vendorId != null)
        'VID ${vendorId!.toRadixString(16).padLeft(4, '0').toUpperCase()}',
      if (productId != null)
        'PID ${productId!.toRadixString(16).padLeft(4, '0').toUpperCase()}',
      if (serialNumber?.trim().isNotEmpty == true) 'SN $serialNumber',
    ];
    return '$portName · $name${ids.isEmpty ? '' : ' · ${ids.join(' / ')}'}';
  }

  ScannerBinding bindingFor(String slot, int baudRate) => ScannerBinding(
    slot: slot,
    portName: portName,
    baudRate: baudRate,
    vendorId: vendorId,
    productId: productId,
    serialNumber: serialNumber,
    productName: productName,
  );

  static List<SerialScannerDevice> discover() {
    final devices = <SerialScannerDevice>[];
    for (final name in SerialPort.availablePorts) {
      final port = SerialPort(name);
      try {
        devices.add(
          SerialScannerDevice(
            portName: name,
            vendorId: port.vendorId,
            productId: port.productId,
            serialNumber: port.serialNumber,
            productName: port.productName ?? port.description,
            manufacturer: port.manufacturer,
          ),
        );
      } on SerialPortError {
        devices.add(SerialScannerDevice(portName: name));
      } finally {
        port.dispose();
      }
    }
    return devices;
  }
}

class SerialScannerService {
  SerialScannerService._({required this._reader});

  final LeitorSerialIsolado _reader;
  final ScannerFrameDecoder _decoder = ScannerFrameDecoder();
  final StreamController<String> _codes = StreamController.broadcast();
  StreamSubscription<Uint8List>? _subscription;

  Stream<String> get codes => _codes.stream;

  static Future<SerialScannerService> open(ScannerBinding binding) async {
    final port = SerialPort(binding.portName);
    try {
      _validateHardwareIdentity(port, binding);
      if (!port.openRead()) {
        throw StateError(
          'Não foi possível reservar ${binding.portName}: '
          '${SerialPort.lastError?.message ?? 'porta ocupada ou indisponível'}.',
        );
      }
      final config = SerialPortConfig()
        ..baudRate = binding.baudRate
        ..bits = 8
        ..parity = SerialPortParity.none
        ..stopBits = 1;
      port.config = config;
      // O mesmo leitor da balança (`leitor_serial_isolado.dart`): o da
      // biblioteca não parava o isolate e derrubava o app no Linux.
      final reader = LeitorSerialIsolado(
        endereco: port.address,
        liberarPorta: () {
          if (port.isOpen) port.close();
          port.dispose();
        },
      );
      final service = SerialScannerService._(reader: reader);
      service._subscription = reader.dados.listen((bytes) {
        for (final code in service._decoder.add(bytes)) {
          service._codes.add(code);
        }
      }, onError: service._codes.addError);
      await reader.iniciar();
      return service;
    } catch (_) {
      if (port.isOpen) port.close();
      port.dispose();
      rethrow;
    }
  }

  static void _validateHardwareIdentity(
    SerialPort port,
    ScannerBinding binding,
  ) {
    final mismatches = <String>[];
    if (binding.vendorId != null && port.vendorId != binding.vendorId) {
      mismatches.add('VID');
    }
    if (binding.productId != null && port.productId != binding.productId) {
      mismatches.add('PID');
    }
    final expectedSerial = binding.serialNumber?.trim();
    if (expectedSerial?.isNotEmpty == true &&
        port.serialNumber?.trim() != expectedSerial) {
      mismatches.add('número de série');
    }
    if (mismatches.isNotEmpty) {
      throw StateError(
        '${binding.portName} agora identifica outro equipamento '
        '(${mismatches.join(', ')} divergente). Refazer o vínculo é obrigatório.',
      );
    }
  }

  Future<void> close() async {
    await _subscription?.cancel();
    _subscription = null;
    // Para o isolate e só então libera a porta (`leitor_serial_isolado.dart`).
    await _reader.parar();
    await _codes.close();
  }
}

/// Converts scanner bytes into one code per CR/LF-terminated frame.
class ScannerFrameDecoder {
  ScannerFrameDecoder({this.maximumLength = 160});

  final int maximumLength;
  final StringBuffer _buffer = StringBuffer();

  List<String> add(List<int> bytes) {
    final frames = <String>[];
    for (final byte in bytes) {
      if (byte == 10 || byte == 13) {
        final value = _buffer.toString().trim();
        _buffer.clear();
        if (value.isNotEmpty) frames.add(value);
        continue;
      }
      if (byte >= 32 && byte <= 126) {
        if (_buffer.length >= maximumLength) {
          _buffer.clear();
          continue;
        }
        _buffer.writeCharCode(byte);
      }
    }
    return frames;
  }

  void reset() => _buffer.clear();
}
