import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/storage/session_store.dart';
import 'package:starchef_pdv/core/storage/local_preferences.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';
import 'package:starchef_pdv/core/widgets/shadcn_layout.dart';
import 'package:starchef_pdv/features/devices/presentation/printer_selection_dialog.dart';
import 'package:starchef_pdv/features/devices/presentation/device_list_page.dart';
import 'package:starchef_pdv/features/auth/data/auth_repository.dart';
import 'package:starchef_pdv/features/auth/domain/auth_session.dart';
import 'package:starchef_pdv/features/auth/presentation/auth_controller.dart';
import 'package:starchef_pdv/features/auth/presentation/login_page.dart';
import 'package:starchef_pdv/features/home/presentation/pdv_settings_menu_dialog.dart';
import 'package:starchef_pdv/features/home/presentation/pdv_cash_center_dialog.dart';
import 'package:starchef_pdv/features/home/presentation/table_details_panel.dart';
import 'package:starchef_pdv/features/orders/presentation/item_void_reason_dialog.dart';
import 'package:starchef_pdv/features/orders/presentation/product_config_dialog.dart';
import 'package:starchef_pdv/features/settings/presentation/api_url_settings_dialog.dart';
import 'package:starchef_pdv/features/settings/presentation/terminal_preferences_dialog.dart';
import 'package:starchef_pdv/features/scale/presentation/scale_workstation_page.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';
import 'package:starchef_pdv/features/topology/presentation/local_topology_dialog.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

void main() {
  group('matriz responsiva das configurações', () {
    testWidgets('menu principal cabe em janela compacta com texto ampliado', (
      tester,
    ) async {
      await _openDialog(
        tester,
        size: const Size(360, 520),
        textScaleFactor: 1.25,
        open: (context) => PdvSettingsMenuDialog.show(
          context,
          canManageDevices: true,
          topologyStatus:
              'Caixa Principal indisponível; verifique a rede local da unidade.',
          offlinePendingCount: 128,
          isDark: true,
          isFullScreen: false,
        ),
      );

      expect(find.text('Configurações do PDV'), findsOneWidget);
      expect(find.text('Preferências deste terminal'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('preferências do terminal rolam sem overflow', (tester) async {
      final directory = Directory.systemTemp.createTempSync(
        'starchef-layout-preferences-',
      );
      addTearDown(() {
        if (directory.existsSync()) directory.deleteSync(recursive: true);
      });
      final preferences = LocalPreferences(
        file: File(
          '${directory.path}${Platform.pathSeparator}preferences.json',
        ),
      );
      await _openDialog(
        tester,
        size: const Size(420, 520),
        textScaleFactor: 1.2,
        open: (context) => showDialog<void>(
          context: context,
          builder: (_) => TerminalPreferencesDialog(
            preferences: preferences,
            detectedPorts: const [],
          ),
        ),
      );

      expect(find.text('Preferências deste terminal'), findsOneWidget);
      expect(find.text('Tempo para ler a comanda'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('URL da API cabe na menor largura suportada', (tester) async {
      final directory = Directory.systemTemp.createTempSync(
        'starchef-layout-api-',
      );
      addTearDown(() {
        if (directory.existsSync()) directory.deleteSync(recursive: true);
      });
      final preferences = LocalPreferences(
        file: File(
          '${directory.path}${Platform.pathSeparator}preferences.json',
        ),
      );
      await _openDialog(
        tester,
        size: const Size(320, 480),
        textScaleFactor: 1.15,
        open: (context) => ApiUrlSettingsDialog.show(
          context,
          preferences,
          'https://api.starchef.com.br/api/v1',
        ),
      );

      expect(find.text('URL da API'), findsWidgets);
      expect(tester.takeException(), isNull);
    });

    testWidgets('seleção de impressora aceita textos longos', (tester) async {
      await _openDialog(
        tester,
        size: const Size(360, 480),
        textScaleFactor: 1.2,
        open: (context) => showDialog<String>(
          context: context,
          builder: (_) => const PrinterSelectionDialog(
            printers: [
              {
                'id': 'printer-1',
                'name': 'Impressora térmica principal do balcão de atendimento',
                'connection_type': 'Windows',
              },
            ],
            title: 'Imprimir recibo de venda',
            summary: 'Pedido #123456 · Mesa com identificação extensa',
            description:
                'A impressão será encaminhada para o equipamento selecionado.',
          ),
        ),
      );

      expect(find.text('Imprimir recibo de venda'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('rede local fornece Material aos campos e permanece rolável', (
      tester,
    ) async {
      await _openDialog(
        tester,
        size: const Size(420, 560),
        textScaleFactor: 1.2,
        open: (context) => showLocalTopologyDialog(
          context: context,
          config: const LocalTopologyConfig(
            mode: LocalTopologyMode.client,
            nodeId: 'terminal-1',
            principalHost: '192.168.1.10',
            port: LocalTopologyConfig.defaultPort,
            pairingSecret: '',
          ),
          status: const LocalTopologyStatus(
            phase: LocalTopologyPhase.unavailable,
            message: 'Caixa Principal indisponível',
          ),
          canEdit: true,
        ),
      );

      expect(find.text('Rede local de caixas'), findsOneWidget);
      expect(find.byType(TextField), findsNWidgets(3));
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('cabeçalho compartilhado empilha ações em largura compacta', (
    tester,
  ) async {
    await _pumpAtSize(
      tester,
      size: const Size(360, 600),
      textScaleFactor: 1.25,
      child: AppPageHeader(
        title: 'Configuração dos equipamentos desta unidade',
        description:
            'Cadastre, teste e mantenha os dispositivos usados neste terminal.',
        leading: const Icon(Icons.settings_outlined),
        actions: [
          OutlinedButton(onPressed: () {}, child: const Text('Atualizar')),
          OutlinedButton(onPressed: () {}, child: const Text('Diagnóstico')),
          FilledButton(onPressed: () {}, child: const Text('Novo equipamento')),
        ],
      ),
    );

    expect(find.text('Novo equipamento'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'página operacional pode ocultar o cabeçalho sem perder o corpo',
    (tester) async {
      await _pumpAtSize(
        tester,
        size: const Size(900, 600),
        textScaleFactor: 1,
        child: const AppPageScaffold(
          title: 'Configuração da balança',
          description: 'Selecione os equipamentos.',
          showHeader: false,
          padding: EdgeInsets.zero,
          body: Text('Operação em andamento'),
        ),
      );

      expect(find.text('Configuração da balança'), findsNothing);
      expect(find.text('Operação em andamento'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  group('matriz responsiva dos pedidos', () {
    testWidgets(
      'cancelamento de item cabe com nome e escala de texto grandes',
      (tester) async {
        await _openDialog(
          tester,
          size: const Size(320, 480),
          textScaleFactor: 1.25,
          open: (context) => ItemVoidReasonDialog.show(
            context,
            itemName:
                'Hambúrguer artesanal completo com acompanhamento especial',
          ),
        );

        expect(find.text('Remover item'), findsWidgets);
        expect(find.text('Produto indisponível'), findsOneWidget);
        expect(tester.takeException(), isNull);

        await tester.tap(find.text('Voltar'));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
      },
    );

    testWidgets('produto com muitas opções continua rolável em janela baixa', (
      tester,
    ) async {
      await _openDialog(
        tester,
        size: const Size(360, 520),
        textScaleFactor: 1.2,
        open: (context) => showProductConfigDialog(context, {
          'name': 'Pizza artesanal tamanho família',
          'requires_variation': true,
          'variations': [
            for (var index = 1; index <= 4; index++)
              {
                'id': 'variation-$index',
                'name': 'Tamanho especial $index',
                'price_delta': index * 3,
              },
          ],
          'addons': [
            for (var index = 1; index <= 8; index++)
              {
                'id': 'addon-$index',
                'name': 'Adicional artesanal número $index',
                'price': index * 1.5,
              },
          ],
        }),
      );

      expect(find.text('Pizza artesanal tamanho família'), findsOneWidget);
      expect(find.text('Adicionais'), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('Cancelar'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('produto por quilo solicita peso em vez de quantidade', (
      tester,
    ) async {
      ProductConfigResult? result;
      await _openDialog(
        tester,
        size: const Size(420, 560),
        textScaleFactor: 1,
        open: (context) async {
          result = await showProductConfigDialog(context, {
            'id': 'product-kg',
            'name': 'Buffet por quilo',
            'pricing_unit': 'kg',
            'variations': <Map<String, dynamic>>[],
            'addons': <Map<String, dynamic>>[],
          });
        },
      );

      expect(find.text('Peso'), findsOneWidget);
      expect(find.text('kg'), findsOneWidget);
      expect(find.text('Quantidade'), findsNothing);
      expect(
        tester
            .widget<FilledButton>(
              find.widgetWithText(FilledButton, 'Adicionar'),
            )
            .onPressed,
        isNull,
      );

      await tester.enterText(find.byKey(const Key('product-weight')), '0,375');
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Adicionar'));
      await tester.pumpAndSettle();

      expect(result?.quantity, closeTo(.375, .0001));
      expect(tester.takeException(), isNull);
    });
  });

  testWidgets('pares de campos empilham antes de ficarem estreitos', (
    tester,
  ) async {
    await _pumpAtSize(
      tester,
      size: const Size(340, 420),
      textScaleFactor: 1.2,
      child: const Padding(
        padding: EdgeInsets.all(24),
        child: AppResponsiveFields(
          children: [
            TextField(
              decoration: InputDecoration(
                labelText: 'Validade da leitura',
                suffixText: 'segundos',
              ),
            ),
            TextField(
              decoration: InputDecoration(
                labelText: 'Espera para impressão',
                suffixText: 'segundos',
              ),
            ),
          ],
        ),
      ),
    );

    final fields = find.byType(TextField);
    expect(fields, findsNWidgets(2));
    expect(
      tester.getTopLeft(fields.at(1)).dy,
      greaterThan(tester.getTopLeft(fields.at(0)).dy),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('cadastro de balança cabe com opções longas em tela estreita', (
    tester,
  ) async {
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient((request) async {
        final results = switch (request.url.path) {
          '/api/v1/tables/sectors/' => [
            {
              'id': 'sector-1',
              'name': 'Setor de buffet e atendimento principal da unidade',
            },
          ],
          '/api/v1/printers/' => [
            {
              'id': 'printer-1',
              'name': 'Impressora térmica principal do balcão de pesagem',
            },
          ],
          '/api/v1/menu/products/' => [
            {
              'id': 'product-1',
              'name': 'Buffet especial por quilo com descrição extensa',
            },
          ],
          _ => const <Map<String, dynamic>>[],
        };
        return http.Response(
          jsonEncode({'results': results}),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    final preferences = LocalPreferences(
      file: File(
        '${Directory.systemTemp.path}${Platform.pathSeparator}starchef-layout-device.json',
      ),
    );

    await _pumpAtSize(
      tester,
      size: const Size(380, 640),
      textScaleFactor: 1.15,
      child: DeviceEditPage(
        kind: DeviceKind.scale,
        api: api,
        token: 'token',
        restaurantId: 'restaurant-1',
        preferences: preferences,
        initialSerialPorts: const ['COM123'],
        initialSectors: const [
          {
            'id': 'sector-1',
            'name': 'Setor de buffet e atendimento principal da unidade',
          },
        ],
        initialPrinters: const [
          {
            'id': 'printer-1',
            'name': 'Impressora térmica principal do balcão de pesagem',
          },
        ],
        initialProducts: const [
          {
            'id': 'product-1',
            'name': 'Buffet especial por quilo com descrição extensa',
          },
        ],
        item: const {
          'id': 'scale-1',
          'name': 'Balança do buffet principal',
          'port': 'COM123',
          'sector': 'sector-1',
          'product': 'product-1',
          'printer': 'printer-1',
          'settings': {'baudrate': 9600},
        },
      ),
    );
    await tester.pump(const Duration(milliseconds: 600));

    expect(find.text('Editar balança'), findsOneWidget);
    expect(find.text('Dados do equipamento'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('configuração inicial da Balança Rápida rola em janela baixa', (
    tester,
  ) async {
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient((_) async => http.Response('{}', 200)),
    );
    final preferences = LocalPreferences(
      file: File(
        '${Directory.systemTemp.path}${Platform.pathSeparator}starchef-layout-scale.json',
      ),
    );

    await _pumpAtSize(
      tester,
      size: const Size(360, 520),
      textScaleFactor: 1.2,
      child: ScaleWorkstationPage(
        api: api,
        accessToken: 'token',
        restaurants: const [
          {
            'id': 'restaurant-1',
            'trade_name': 'Unidade principal com nome comercial extenso',
          },
        ],
        restaurantId: null,
        products: const [],
        onRestaurantChanged: (_) async {},
        preferences: preferences,
      ),
    );

    expect(find.text('Estação de balança'), findsOneWidget);
    expect(find.text('Restaurante'), findsOneWidget);
    expect(find.byIcon(Icons.fullscreen_exit), findsNothing);
    expect(find.byIcon(Icons.fullscreen), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('operação da Balança Rápida usa grade 25 50 25', (tester) async {
    await _pumpAtSize(
      tester,
      size: const Size(1200, 700),
      textScaleFactor: 1,
      child: const ScaleOperationGrid(
        items: ColoredBox(color: Colors.blue),
        catalog: ColoredBox(color: Colors.orange),
        command: ColoredBox(color: Colors.green),
      ),
    );

    final items = tester.getRect(find.byKey(const Key('scale-items-column')));
    final catalog = tester.getRect(
      find.byKey(const Key('scale-catalog-column')),
    );
    final command = tester.getRect(
      find.byKey(const Key('scale-command-column')),
    );

    // 1200 px menos os dois espaçamentos de 10 px entre as três colunas,
    // divididos na proporção 25/50/25 — as colunas não ficam mais coladas.
    expect(items.width, closeTo(295, .01));
    expect(catalog.width, closeTo(590, .01));
    expect(command.width, closeTo(295, .01));
    expect(catalog.left - items.right, 10);
    expect(command.left - catalog.right, 10);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'Balança Rápida mantém gap de 10 px quando o catálogo está oculto',
    (tester) async {
      await _pumpAtSize(
        tester,
        size: const Size(1200, 700),
        textScaleFactor: 1,
        child: const ScaleOperationGrid(
          items: ColoredBox(color: Colors.blue),
          catalog: null,
          command: ColoredBox(color: Colors.green),
        ),
      );

      final items = tester.getRect(find.byKey(const Key('scale-items-column')));
      final command = tester.getRect(
        find.byKey(const Key('scale-command-column')),
      );

      expect(find.byKey(const Key('scale-columns-gap')), findsOneWidget);
      expect(command.left - items.right, 10);
      expect(items.width, closeTo(595, .01));
      expect(command.width, closeTo(595, .01));
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('Financeiro empilha ações em janela estreita', (tester) async {
    await _openDialog(
      tester,
      size: const Size(320, 480),
      textScaleFactor: 1.25,
      open: (context) => PdvCashCenterDialog.show(
        context,
        cashSession: const {
          'id': 'cash-1',
          'station':
              'Caixa principal do atendimento frontal com nome muito longo',
        },
        balanceLabel: r'R$ 12.345,67',
      ),
    );

    expect(find.text('Financeiro do caixa'), findsOneWidget);
    expect(find.text('Suprimento'), findsOneWidget);
    expect(find.text('Sangria'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('login compacto mantém formulário e ações acessíveis', (
    tester,
  ) async {
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      client: MockClient((_) async => http.Response('{}', 200)),
    );
    final controller = AuthController(
      AuthRepository(apiClient: api, sessionStore: _MemorySessionStore()),
    );
    final preferences = LocalPreferences(
      file: File(
        '${Directory.systemTemp.path}${Platform.pathSeparator}starchef-layout-login.json',
      ),
    );

    await _pumpAtSize(
      tester,
      size: const Size(320, 520),
      textScaleFactor: 1.2,
      child: LoginPage(
        controller: controller,
        isDark: true,
        onToggleTheme: () {},
        preferences: preferences,
        onClose: () {},
      ),
    );

    expect(find.text('Bem-vindo de volta'), findsOneWidget);
    expect(find.byTooltip('Fechar aplicação'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('detalhes da mesa permanecem legíveis no compacto', (
    tester,
  ) async {
    await _pumpAtSize(
      tester,
      size: const Size(380, 640),
      textScaleFactor: 1.15,
      child: TableDetailsPanel(
        table: const {
          'number': 128,
          'capacity': 12,
          'sector_name':
              'Salão principal e varanda de atendimento preferencial',
          'current_order_id': 'order-1',
          'active_commands': [
            {
              'id': 'command-1',
              'number': 9876,
              'code': 'CMD-9876-EXTENSO',
              'customer_name':
                  'Cliente com nome completo muito extenso para a comanda',
            },
          ],
        },
        onBack: () {},
        onOpenCommand: (_) {},
      ),
    );

    expect(find.text('Mesa 128'), findsOneWidget);
    expect(find.text('Comandas Vinculadas (1)'), findsOneWidget);
    expect(find.text('Transferir Mesa'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}

class _MemorySessionStore implements SessionStore {
  AuthSession? value;

  @override
  Future<void> clear() async => value = null;

  @override
  Future<AuthSession?> read() async => value;

  @override
  Future<void> save(AuthSession session) async => value = session;
}

Future<void> _openDialog(
  WidgetTester tester, {
  required Size size,
  required double textScaleFactor,
  required Future<dynamic> Function(BuildContext context) open,
}) async {
  await _pumpAtSize(
    tester,
    size: size,
    textScaleFactor: textScaleFactor,
    child: Builder(
      builder: (context) => Center(
        child: FilledButton(
          onPressed: () => unawaited(open(context)),
          child: const Text('Abrir'),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Abrir'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

Future<void> _pumpAtSize(
  WidgetTester tester, {
  required Size size,
  required double textScaleFactor,
  required Widget child,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  tester.platformDispatcher.textScaleFactorTestValue = textScaleFactor;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
    tester.platformDispatcher.clearTextScaleFactorTestValue();
  });

  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.dark(),
      builder: (context, child) =>
          ShadTheme(data: AppTheme.shadDark(), child: child!),
      home: Scaffold(body: child),
    ),
  );
  await tester.pump();
}
