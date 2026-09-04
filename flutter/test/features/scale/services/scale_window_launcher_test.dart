import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';
import 'package:starchef_pdv/features/scale/services/scale_window_launcher.dart';

void main() {
  late Directory temporaryDirectory;

  setUp(() async {
    temporaryDirectory = await Directory.systemTemp.createTemp(
      'starchef-scale-handoff-',
    );
    AppPaths.overrideDataDirectory(temporaryDirectory);
  });

  tearDown(() async {
    AppPaths.overrideDataDirectory(null);
    if (await temporaryDirectory.exists()) {
      await temporaryDirectory.delete(recursive: true);
    }
  });

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

    test(
      'transfers the session once without putting tokens in arguments',
      () async {
        const session = AuthSession(
          accessToken: 'access-secret',
          refreshToken: 'refresh-secret',
          user: AuthUser(id: 'user-1', username: 'caixa', name: 'Caixa'),
        );

        final handoff = await ScaleWindowLauncher.prepareSessionHandoff(
          session,
        );
        final arguments = ['--session-handoff=$handoff'];

        expect(arguments.join(' '), isNot(contains('access-secret')));
        expect(arguments.join(' '), isNot(contains('refresh-secret')));
        final restored = await ScaleWindowLauncher.takeSession(arguments);
        expect(restored?.accessToken, session.accessToken);
        expect(restored?.refreshToken, session.refreshToken);
        expect(restored?.user.username, session.user.username);
        expect(await ScaleWindowLauncher.takeSession(arguments), isNull);
      },
    );

    test('refuses a handoff argument containing a path', () async {
      final unrelated = File(
        '${temporaryDirectory.path}${Platform.pathSeparator}unrelated.json',
      );
      await unrelated.writeAsString('{}');

      final restored = await ScaleWindowLauncher.takeSession([
        '--session-handoff=..${Platform.pathSeparator}unrelated.json',
      ]);

      expect(restored, isNull);
      expect(await unrelated.exists(), isTrue);
    });
  });
}
