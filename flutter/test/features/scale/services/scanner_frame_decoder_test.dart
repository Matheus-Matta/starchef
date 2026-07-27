import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/scale/services/serial_scanner_service.dart';

void main() {
  group('ScannerFrameDecoder', () {
    test('emits one frame for each CR or LF terminator', () {
      final decoder = ScannerFrameDecoder();

      final frames = decoder.add('CMD-1\rCMD-2\nCMD-3\r\n\n'.codeUnits);

      expect(frames, ['CMD-1', 'CMD-2', 'CMD-3']);
    });

    test('keeps a fragmented frame until its terminator arrives', () {
      final decoder = ScannerFrameDecoder();

      expect(decoder.add('COM'.codeUnits), isEmpty);
      expect(decoder.add('AND'.codeUnits), isEmpty);
      expect(decoder.add('A-42\r'.codeUnits), ['COMANDA-42']);
    });

    test('ignores non-printable and non-ASCII bytes', () {
      final decoder = ScannerFrameDecoder();

      final frames = decoder.add([
        0,
        31,
        ...'ABC'.codeUnits,
        127,
        128,
        255,
        ...'123'.codeUnits,
        10,
      ]);

      expect(frames, ['ABC123']);
    });

    test('discards a frame that exceeds the configured limit', () {
      final decoder = ScannerFrameDecoder(maximumLength: 4);

      final frames = decoder.add('ABCDE\nOK\r'.codeUnits);

      expect(frames, ['OK']);
    });
  });
}
