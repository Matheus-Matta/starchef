/// Tipos operacionais que o celular pode retirar da fila do backend.
///
/// Mantém os mesmos nomes e aliases de [PrintJobType] do PDV Desktop. Recibos,
/// fechamento de caixa, pesagem, DANFE e testes ficam para o agente do PDV.
abstract final class MobilePrintJobPolicy {
  static const maxAutomaticAttempts = 5;

  static const _newOrderTypes = {'kitchen', 'kitchen_ticket', 'bar_ticket'};

  static const _cancellationTypes = {'kitchen_cancel', 'kitchen_cancellation'};

  /// O filtro que vai NA CONSULTA. Filtrar só depois de receber não basta: a
  /// fila da loja acumula recibos e notas de pesagem que ninguém imprime, e a
  /// primeira página (a mais antiga) nunca chegava às comandas.
  static final queryTypes = [
    ..._newOrderTypes,
    ..._cancellationTypes,
  ].join(',');

  static bool shouldAutomaticallyPrint(Map<String, dynamic> job) {
    final payload = job['payload'];
    if (payload is Map && payload['manual_only'] == true) return false;

    final type = '${job['job_type'] ?? ''}'.trim().toLowerCase();
    return _newOrderTypes.contains(type) || _cancellationTypes.contains(type);
  }
}
