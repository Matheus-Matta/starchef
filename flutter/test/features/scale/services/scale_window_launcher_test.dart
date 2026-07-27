import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/scale/services/scale_window_launcher.dart';

void main() {
  group('ScaleWindowLauncher arguments', () {
    test('recognizes only the dedicated workstation flag', () {
      expect(
        ScaleWindowLauncher.isScaleWindow(const ['--scale-workstation']),
        isTrue,
      );
      expect(
        ScaleWindowLauncher.isScaleWindow(const ['--restaurant=restaurant-1']),
        isFalse,
      );
    });

    test('extracts a normalized restaurant without exposing session data', () {
      const arguments = [
        '--scale-workstation',
        '--restaurant=  restaurant-1  ',
      ];

      expect(ScaleWindowLauncher.restaurantFrom(arguments), 'restaurant-1');
      expect(arguments.join(' '), isNot(contains('token')));
    });

    test('ignores an empty restaurant argument', () {
      expect(
        ScaleWindowLauncher.restaurantFrom(const [
          '--scale-workstation',
          '--restaurant=   ',
        ]),
        isNull,
      );
    });
  });
}
