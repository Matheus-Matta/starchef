part of 'mobile_print_agent.dart';

extension _MobilePrintAgentRetry on MobilePrintAgent {
  Future<bool> _adiar(String jobId, String error) async {
    final vezes = (_falhas[jobId] ?? 0) + 1;
    _falhas[jobId] = vezes.clamp(0, MobilePrintJobPolicy.maxAutomaticAttempts);
    _errosImpressao[jobId] = error;
    try {
      await attempts.save(jobId, _falhas[jobId]!);
    } catch (_) {
      // Falha local de disco não pode interromper a impressão dos próximos.
    }
    if (vezes >= MobilePrintJobPolicy.maxAutomaticAttempts) {
      return _registrarFalhaFinal(jobId);
    }
    const esperasSegundos = [3, 8, 15, 30];
    final segundos = esperasSegundos[(vezes - 1).clamp(0, 3)];
    _retryAfter[jobId] = DateTime.now().add(Duration(seconds: segundos));
    return false;
  }

  Future<bool> _registrarFalhaFinal(String jobId) async {
    final tentativas =
        _falhas[jobId] ?? MobilePrintJobPolicy.maxAutomaticAttempts;
    final ultimoErro = _errosImpressao[jobId] ?? 'A impressora não respondeu.';
    final mensagem =
        'Impressão encerrada após $tentativas tentativas. '
        'Último erro: $ultimoErro';
    try {
      await api.post(
        '/print-jobs/$jobId/mark-failed/',
        body: {'error': mensagem},
      );
    } catch (error) {
      _lastError =
          'Limite de tentativas atingido; falha aguardando registro: $error';
      _retryAfter[jobId] = DateTime.now().add(const Duration(seconds: 30));
      return false;
    }
    _retryAfter.remove(jobId);
    _falhas.remove(jobId);
    _errosImpressao.remove(jobId);
    try {
      await attempts.remove(jobId);
    } catch (_) {
      // A fila já foi encerrada no backend; o arquivo local é só um espelho.
    }
    _lastError = mensagem;
    return true;
  }
}
