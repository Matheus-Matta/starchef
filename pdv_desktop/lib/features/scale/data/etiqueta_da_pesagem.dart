import '../../../core/network/api_client.dart';
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
  }) : _enviar = enviar ?? _enviarDeVerdade;

  final ApiClient api;
  final String accessToken;
  final Future<void> Function(
    Map<String, dynamic> impressora,
    PrintDocument documento,
  )
  _enviar;

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
    await api.post(
      '/print-jobs/$id/mark-printed/',
      body: const {},
      accessToken: accessToken,
    );
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
