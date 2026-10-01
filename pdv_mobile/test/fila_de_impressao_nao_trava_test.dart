import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/api_client.dart';
import 'package:starchef_pdv_mobile/core/network/api_exception.dart';
import 'package:starchef_pdv_mobile/features/printing/domain/mobile_printer.dart';
import 'package:starchef_pdv_mobile/features/printing/services/mobile_print_agent.dart';
import 'package:starchef_pdv_mobile/features/printing/services/nearby_printer_permission.dart';
import 'package:starchef_pdv_mobile/features/printing/services/network_printer_writer.dart';
import 'package:starchef_pdv_mobile/features/printing/services/print_confirmation_store.dart';

/// Um trabalho com problema não pode segurar a fila do salão.
///
/// A fila é lida do mais antigo para o mais novo. Um erro no primeiro (reserva
/// recusada, impressora desligada) interrompia o ciclo inteiro — e como ele
/// continuava sendo o mais antigo, NENHUM pedido novo imprimia, ciclo após
/// ciclo.
Map<String, dynamic> _impressora(String id, String host) => {
  'id': id,
  'name': id,
  'connection_type': 'network',
  'driver_type': 'escpos',
  'host': host,
  'port': 9100,
  'timeout_seconds': 1,
  'is_active': true,
  'auto_print': true,
};

Map<String, dynamic> _job(String id, String printer) => {
  'id': id,
  'printer': printer,
  'job_type': 'kitchen_ticket',
  'payload': {'text_content': 'Pedido $id'},
};

class _Api extends ApiClient {
  _Api(this.jobs, {this.reservaQuebrada = const {}})
    : super(baseUrlProvider: () => 'https://example.test/api/v1');

  final List<Map<String, dynamic>> jobs;
  final Set<String> reservaQuebrada;
  final posts = <String>[];

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, dynamic>? query,
    String? accessToken,
  }) async => path == '/printers/'
      ? {
          'results': [
            _impressora('cozinha', '10.0.0.5'),
            _impressora('bar', '10.0.0.6'),
          ],
        }
      : {'results': jobs};

  @override
  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
    String? idempotencyKey,
  }) async {
    posts.add(path);
    final id = path.split('/')[2];
    if (path.endsWith('/claim/') && reservaQuebrada.contains(id)) {
      throw const ApiException('Estado inválido do cupom.', statusCode: 400);
    }
    return {};
  }
}

class _Escritor extends NetworkPrinterWriter {
  _Escritor({this.desligada = const {}});

  final Set<String> desligada;
  final tentativas = <String>[];

  @override
  Future<void> write(MobilePrinter printer, List<int> bytes) async {
    tentativas.add(printer.id);
    if (desligada.contains(printer.id)) throw Exception('sem resposta');
  }
}

class _Permitido extends NearbyPrinterPermission {
  const _Permitido();
  @override
  Future<bool> request() async => true;
}

class _Memoria implements PrintConfirmationStorage {
  final ids = <String>{};
  @override
  Future<void> add(String jobId) async => ids.add(jobId);
  @override
  Future<Set<String>> load() async => Set.of(ids);
  @override
  Future<void> remove(String jobId) async => ids.remove(jobId);
}

Future<void> _rodar(_Api api, _Escritor escritor) async {
  final agente = MobilePrintAgent(
    api: api,
    permission: const _Permitido(),
    writer: escritor,
    confirmations: _Memoria(),
  );
  await agente.start('r1');
  agente.stop();
}

void main() {
  test('trabalho com erro na reserva não impede o próximo de imprimir', () async {
    final api = _Api(
      [_job('velho', 'cozinha'), _job('novo', 'cozinha')],
      reservaQuebrada: {'velho'},
    );
    final escritor = _Escritor();

    await _rodar(api, escritor);

    expect(api.posts, contains('/print-jobs/novo/mark-printed/'));
    expect(escritor.tentativas, ['cozinha']);
  });

  test('impressora desligada é tentada uma vez e não segura a outra', () async {
    final api = _Api([
      _job('c1', 'cozinha'),
      _job('c2', 'cozinha'),
      _job('c3', 'cozinha'),
      _job('b1', 'bar'),
    ]);
    final escritor = _Escritor(desligada: {'cozinha'});

    await _rodar(api, escritor);

    expect(escritor.tentativas, ['cozinha', 'bar']);
    expect(api.posts, contains('/print-jobs/b1/mark-printed/'));
    expect(api.posts, contains('/print-jobs/c1/release/'));
  });
}
