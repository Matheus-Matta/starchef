import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';
import 'package:starchef_pdv/features/home/presentation/command_table_selection_dialog.dart';

void main() {
  const command = <String, dynamic>{'id': 'command-8', 'number': 8};
  const tables = <Map<String, dynamic>>[
    {
      'id': 'table-1',
      'number': 1,
      'status': 'free',
      'is_active': true,
      'active_commands': <dynamic>[],
    },
    {
      'id': 'table-2',
      'number': 2,
      'status': 'occupied',
      'is_active': true,
      'active_commands': <dynamic>['command-3'],
    },
    {
      'id': 'table-3',
      'number': 3,
      'status': 'cleaning',
      'is_active': true,
      'active_commands': <dynamic>[],
    },
  ];

  test('pede mesa para comanda em uso que ainda não possui vínculo', () {
    expect(
      commandNeedsTableSelection(const {
        'status': 'occupied',
        'current_order_id': 'order-1',
        'current_table': null,
      }),
      isTrue,
    );
    expect(
      commandNeedsTableSelection(const {
        'status': 'occupied',
        'current_order_id': 'order-1',
        'current_table': 'table-1',
      }),
      isFalse,
    );
  });

  testWidgets('permite vincular mesa livre ou ocupada antes de abrir', (
    tester,
  ) async {
    CommandTableSelection? result;
    await _pumpDialogHost(
      tester,
      onResult: (value) => result = value,
      command: command,
      tables: tables,
    );

    await tester.tap(find.text('Abrir comanda'));
    await tester.pumpAndSettle();

    expect(find.text('Comanda 8 sem mesa'), findsOneWidget);
    expect(find.text('Mesa 1'), findsOneWidget);
    expect(find.text('Mesa 2'), findsOneWidget);
    expect(find.text('Ocupada · 1 comanda vinculada'), findsOneWidget);
    expect(find.text('Mesa 3'), findsNothing);

    final confirmBeforeSelection = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Vincular'),
    );
    expect(confirmBeforeSelection.onPressed, isNull);

    await tester.tap(find.text('Mesa 2'));
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Vincular'));
    await tester.pumpAndSettle();

    expect(result?.table?['id'], 'table-2');
    expect(tester.takeException(), isNull);
  });

  testWidgets('permite confirmar a abertura sem mesa', (tester) async {
    CommandTableSelection? result;
    await _pumpDialogHost(
      tester,
      onResult: (value) => result = value,
      command: command,
      tables: tables,
    );

    await tester.tap(find.text('Abrir comanda'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sem mesa'));
    await tester.pumpAndSettle();

    expect(result, isNotNull);
    expect(result?.table, isNull);
    expect(tester.takeException(), isNull);
  });
}

Future<void> _pumpDialogHost(
  WidgetTester tester, {
  required ValueChanged<CommandTableSelection?> onResult,
  required Map<String, dynamic> command,
  required List<Map<String, dynamic>> tables,
}) async {
  tester.view.physicalSize = const Size(900, 700);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });

  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFFF57C00),
      ),
      home: ShadTheme(
        data: AppTheme.shadLight(),
        child: Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: FilledButton(
                onPressed: () async {
                  onResult(
                    await showDialog<CommandTableSelection>(
                      context: context,
                      builder: (_) => CommandTableSelectionDialog(
                        command: command,
                        tables: tables,
                      ),
                    ),
                  );
                },
                child: const Text('Abrir comanda'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pump();
}
