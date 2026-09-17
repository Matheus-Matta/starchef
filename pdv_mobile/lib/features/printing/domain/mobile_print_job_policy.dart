/// Tipos operacionais que o celular pode retirar da fila do backend.
///
/// Mantém os mesmos nomes e aliases de [PrintJobType] do PDV Desktop. Recibos,
/// fechamento de caixa, pesagem, DANFE e testes ficam para o agente do PDV.
abstract final class MobilePrintJobPolicy {
  static const _newOrderTypes = {'kitchen', 'kitchen_ticket', 'bar_ticket'};

  static const _cancellationTypes = {'kitchen_cancel', 'kitchen_cancellation'};

  static bool shouldAutomaticallyPrint(Map<String, dynamic> job) {
    final payload = job['payload'];
    if (payload is Map && payload['manual_only'] == true) return false;

    final type = '${job['job_type'] ?? ''}'.trim().toLowerCase();
    return _newOrderTypes.contains(type) || _cancellationTypes.contains(type);
  }
}
