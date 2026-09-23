import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/storage/local_preferences.dart';
import 'package:starchef_pdv_desktop/core/storage/session_store.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/core/update/pdv_update_service.dart';
import 'package:starchef_pdv_desktop/features/auth/data/auth_repository.dart';
import 'package:starchef_pdv_desktop/features/auth/domain/auth_session.dart';
import 'package:starchef_pdv_desktop/features/auth/presentation/auth_controller.dart';
import 'package:starchef_pdv_desktop/features/auth/presentation/login_page.dart';
import 'package:starchef_pdv_desktop/features/devices/printing/printer.dart';
import 'package:starchef_pdv_desktop/features/home/presentation/pdv_operational_chrome.dart';

const _atualizado = PdvUpdateStatus(
  phase: PdvUpdatePhase.upToDate,
  installed: PdvInstalledVersion(version: '3.0.33', buildNumber: '34'),
  latestVersion: '3.0.33',
);

void main() {
  testWidgets('login mostra versão instalada e que ela está atualizada', (
    tester,
  ) async {
    final directory = Directory.systemTemp.createTempSync(
      'starchef-login-version-',
    );
    addTearDown(() {
      if (directory.existsSync()) directory.deleteSync(recursive: true);
    });
    final controller = AuthController(
      AuthRepository(
        apiClient: ApiClient(
          baseUrl: 'http://starchef.test/api/v1',
          client: MockClient((_) async => http.Response('{}', 200)),
        ),
        sessionStore: _MemorySessionStore(),
      ),
    );

    await _pump(
      tester,
      LoginPage(
        controller: controller,
        isDark: false,
        onToggleTheme: () {},
        preferences: LocalPreferences(
          file: File('${directory.path}${Platform.pathSeparator}prefs.json'),
        ),
        versionStatus: _atualizado,
      ),
    );

    expect(find.text('v3.0.33 · Atualizado'), findsOneWidget);
    expect(find.textContaining('+34'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('barra interna mostra versão e atualização disponível', (
    tester,
  ) async {
    await _pump(
      tester,
      PdvOperationalBar(
        cashName: 'Caixa principal',
        operatorName: 'Ana',
        shiftLabel: 'Turno desde 08:00',
        cashOpen: true,
        network: const NetworkStatus(phase: NetworkPhase.online),
        printer: ValueNotifier(PrinterAvailability.available),
        syncPending: false,
        versionStatus: const PdvUpdateStatus(
          phase: PdvUpdatePhase.updateAvailable,
          installed: PdvInstalledVersion(version: '3.0.33'),
          latestVersion: '3.0.34',
        ),
      ),
    );

    expect(find.text('v3.0.33 · Atualização disponível'), findsOneWidget);
    expect(find.byTooltip('Nova versão: v3.0.34'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _MemorySessionStore implements SessionStore {
  @override
  Future<void> clear() async {}

  @override
  Future<AuthSession?> read() async => null;

  @override
  Future<void> save(AuthSession session) async {}
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  tester.view.physicalSize = const Size(1280, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.light(),
      builder: (context, child) =>
          ShadTheme(data: AppTheme.shadLight(), child: child!),
      home: Scaffold(body: child),
    ),
  );
  await tester.pump();
}
