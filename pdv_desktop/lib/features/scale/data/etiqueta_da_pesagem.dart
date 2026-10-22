import '../../../core/network/api_client.dart';
import '../../../core/logging/app_logger.dart';
import '../../../core/network/api_exception.dart';
import '../../devices/printing/print_document.dart';
import '../../devices/printing/printer_device.dart';
import '../../devices/printing/printer.dart';

/// A etiqueta não saiu; `motivo` é o que o operador lê.
class FalhaNaEtiqueta implements Exception {
  const FalhaNaEtiqueta(this.motivo);

  final String motivo;

  @override
  String toString() => motivo;
}

/// A Balança Rápida imprime a PRÓPRIA etiqueta e confirma no servidor.
///
/// Antes ela só criava o trabalho e esperava um PDV imprimir. Qualquer PDV do
/// restaurante podia reservá-lo: com a impressora USB/serial ligada no PC da
/// balança, outro PC reservava, tentava a porta dele e a etiqueta não saía.
/// Agora o trabalho nasce reservado para esta estação (`imprime_aqui`) e é
/// impresso aqui. Se falhar, fica `failed` com o motivo — visível, e o botão
/// Reimprimir tenta de novo.
class EtiquetaDaPesagem {
  EtiquetaDaPesagem(
    this.api, {
    required this.accessToken,
    Future<void> Function(Map<String, dynamic> impressora, PrintDocument doc)?
    enviar,
    Future<void> Function(Duration pausa)? esperar,
  }) : _enviar = enviar ?? _enviarDeVerdade,
       _esperar = esperar ?? Future<void>.delayed;

  final ApiClient api;
  final String accessToken;
  final Future<void> Function(
    Map<String, dynamic> impressora,
    PrintDocument documento,
  )
  _enviar;
  final Future<void> Function(Duration pausa) _esperar;

  /// As pausas entre as tentativas de confirmar (`mark-printed`).
  static const pausasDaConfirmacao = [
    Duration(seconds: 2),
    Duration(seconds: 5),
    Duration(seconds: 15),
    Duration(seconds: 30),
  ];

  /// A confirmação em segundo plano, para quem quiser esperar (os testes).
  Future<void> confirmando = Future.value();

  Future<void> imprimir({
    required Map<String, dynamic> job,
    required Map<String, dynamic>? impressora,
  }) async {
    final id = '${job['id']}';
    if (impressora == null) {
      const motivo =
          'A impressora da balança não está cadastrada neste restaurante.';
      await _marcarFalha(id, motivo);
      throw const FalhaNaEtiqueta(motivo);
    }
    try {
      await _enviar(impressora, PrintDocument.fromRemoteJob(job));
    } catch (erro) {
      final motivo = '$erro';
      await _marcarFalha(id, motivo);
      throw FalhaNaEtiqueta(motivo);
    }
    // Saiu no papel: a confirmação INSISTE em segundo plano. Desistir na
    // primeira falha deixava a reserva vencer, o trabalho voltar à fila e um
    // PDV imprimir de novo a cada confirmação perdida ("a comanda 7 saiu umas
    // 5 vezes"). Repetir é seguro: marcar como impressa é idempotente.
    confirmando = _confirmar(id);
  }

  Future<void> _confirmar(String id) async {
    for (var tentativa = 0; ; tentativa++) {
      try {
        await api.post(
          '/print-jobs/$id/mark-printed/',
          body: const {},
          accessToken: accessToken,
        );
        return;
      } on ApiException catch (erro) {
        if (tentativa >= pausasDaConfirmacao.length) {
          AppLogger.instance.warning(
            'scale_ticket_confirm_failed',
            data: {'job': id, 'message': erro.message},
          );
          return;
        }
        await _esperar(pausasDaConfirmacao[tentativa]);
      }
    }
  }

  /// Reserva de novo um trabalho reenfileirado (Reimprimir) para esta estação.
  Future<Map<String, dynamic>> reservar(String id) => api.post(
    '/print-jobs/$id/claim/',
    body: const {},
    accessToken: accessToken,
  );

  Future<void> _marcarFalha(String id, String motivo) async {
    try {
      await api.post(
        '/print-jobs/$id/mark-failed/',
        body: {'error': motivo},
        accessToken: accessToken,
      );
    } on ApiException {
      // Sem rede para marcar: a reserva expira em 5 min e o trabalho volta
      // para a fila dos PDVs (`_release_stale_claims`).
    }
  }

  static Future<void> _enviarDeVerdade(
    Map<String, dynamic> impressora,
    PrintDocument documento,
  ) => ReceiptPrinter(PrinterDevice.fromJson(impressora)).send(documento);
}
