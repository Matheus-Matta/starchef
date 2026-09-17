import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/api_exception.dart';
import 'package:starchef_pdv_mobile/features/printing/domain/mobile_print_job_policy.dart';
import 'package:starchef_pdv_mobile/features/printing/domain/mobile_printer.dart';
import 'package:starchef_pdv_mobile/features/printing/services/mobile_print_agent.dart';
import 'package:starchef_pdv_mobile/features/printing/services/nearby_printer_permission.dart';
import 'package:starchef_pdv_mobile/features/printing/services/network_printer_writer.dart';
import 'package:starchef_pdv_mobile/features/printing/services/print_confirmation_store.dart';

void main() {
  test('aceita somente nova comanda e cancelamento operacional', () {
    for (final type in [
      'kitchen',
      'kitchen_ticket',
      'bar_ticket',
      'kitchen_cancel',
      'kitchen_cancellation',
    ]) {
      expect(
        MobilePrintJobPolicy.shouldAutomaticallyPrint({'job_type': type}),
        isTrue,
      );
    }
    for (final type in [
      'receipt',
      'table_bill',
      'cash_close',
      'weigh_ticket',
      'fiscal_danfe',
      'printer_test',
    ]) {
      expect(
        MobilePrintJobPolicy.shouldAutomaticallyPrint({'job_type': type}),
        isFalse,
      );
    }
  });

  test('ignora trabalho marcado para impressão manual', () {
    expect(
      MobilePrintJobPolicy.shouldAutomaticallyPrint({
        'job_type': 'kitchen_ticket',
        'payload': {'manual_only': true},
      }),
      isFalse,
    );
  });

  test('reserva, imprime e confirma um trabalho do backend', () async {
    final api = _FakeApi();
    final writer = _FakeWriter();
    final agent = MobilePrintAgent(
      api: api,
      permission: const _GrantedPermission(),
      writer: writer,
      confirmations: _MemoryConfirmations(),
    );

    await agent.start('restaurant-1');
    agent.stop();

    expect(api.posts, [
      '/print-jobs/job-1/claim/',
      '/print-jobs/job-1/mark-printed/',
    ]);
    expect(writer.writes, hasLength(1));
    expect(writer.writes.single.$1.host, '192.168.1.50');
    expect(writer.writes.single.$2, containsAllInOrder([0x1b, 0x40]));
  });

  test('libera a reserva quando a impressora de rede falha', () async {
    final api = _FakeApi();
    final writer = _FakeWriter(fail: true);
    final agent = MobilePrintAgent(
      api: api,
      permission: const _GrantedPermission(),
      writer: writer,
      confirmations: _MemoryConfirmations(),
    );

    await agent.start('restaurant-1');
    agent.stop();

    expect(api.posts, contains('/print-jobs/job-1/release/'));
    expect(api.posts, isNot(contains('/print-jobs/job-1/mark-printed/')));
  });

  test('não imprime de novo quando só a confirmação HTTP falha', () async {
    final api = _FakeApi(failFirstMark: true);
    final writer = _FakeWriter();
    final confirmations = _MemoryConfirmations();
    final agent = MobilePrintAgent(
      api: api,
      permission: const _GrantedPermission(),
      writer: writer,
      confirmations: confirmations,
    );

    await agent.start('restaurant-1');
    agent.stop();
    await agent.start('restaurant-1');
    agent.stop();

    expect(writer.writes, hasLength(1));
    expect(api.posts, isNot(contains('/print-jobs/job-1/release/')));
    expect(confirmations.ids, isEmpty);
  });
}

class _FakeApi extends ApiClient {
  _FakeApi({this.failFirstMark = false})
    : super(baseUrlProvider: () => 'https://example.test/api/v1');

  final posts = <String>[];
  final bool failFirstMark;
  bool marked = false;
  bool _markFailed = false;

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) async {
    if (path == '/printers/') {
      return {
        'results': [
          {
            'id': 'printer-1',
            'name': 'Cozinha',
            'connection_type': 'network',
            'driver_type': 'escpos',
            'host': '192.168.1.50',
            'port': 9100,
            'timeout_seconds': 2,
            'is_active': true,
            'auto_print': true,
          },
        ],
      };
    }
    if (path == '/print-jobs/' && query?['status'] == 'pending') {
      if (marked) return {'results': <Object>[]};
      return {
        'results': [
          {
            'id': 'job-1',
            'printer': 'printer-1',
            'job_type': 'kitchen_ticket',
            'payload': {'text_content': 'Pedido 10'},
          },
        ],
      };
    }
    return {'results': <Object>[]};
  }

  @override
  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
    String? idempotencyKey,
  }) async {
    posts.add(path);
    if (path.endsWith('/mark-printed/')) {
      if (failFirstMark && !_markFailed) {
        _markFailed = true;
        throw const ApiException('offline', isConnectivity: true);
      }
      marked = true;
    }
    return <String, dynamic>{};
  }
}

class _FakeWriter extends NetworkPrinterWriter {
  _FakeWriter({this.fail = false});

  final bool fail;
  final writes = <(MobilePrinter, List<int>)>[];

  @override
  Future<void> write(MobilePrinter printer, List<int> bytes) async {
    writes.add((printer, bytes));
    if (fail) throw Exception('sem papel');
  }
}

class _GrantedPermission extends NearbyPrinterPermission {
  const _GrantedPermission();

  @override
  Future<bool> request() async => true;
}

class _MemoryConfirmations implements PrintConfirmationStorage {
  final ids = <String>{};

  @override
  Future<void> add(String jobId) async => ids.add(jobId);

  @override
  Future<Set<String>> load() async => Set.of(ids);

  @override
  Future<void> remove(String jobId) async => ids.remove(jobId);
}
