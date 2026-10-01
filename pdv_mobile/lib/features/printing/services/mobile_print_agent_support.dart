part of 'mobile_print_agent.dart';

extension _MobilePrintAgentSupport on MobilePrintAgent {
  Future<List<Map<String, dynamic>>> _loadQueue() async {
    final restaurant = _restaurantId;
    if (restaurant == null) return const [];
    final page = await api.get(
      '/print-jobs/',
      query: {
        'restaurant': restaurant,
        'status__in': 'pending,rendered,claimed,failed',
        'job_type__in': MobilePrintJobPolicy.queryTypes,
        'ordering': 'created_at',
        'page_size': 100,
      },
    );
    return _rows(page);
  }

  Future<void> _processJobs(String restaurant) async {
    final available = {
      for (final printer in _printers)
        if (printer.acceptsAutomaticJobs) printer.id: printer,
    };
    if (available.isEmpty) return;
    final page = await api.get(
      '/print-jobs/',
      query: {
        'restaurant': restaurant,
        'status__in': 'pending,rendered',
        'job_type__in': MobilePrintJobPolicy.queryTypes,
        'printer__in': available.keys.join(','),
        'ordering': 'created_at',
        'page_size': 100,
      },
    );
    // O que já falhou vai para o FIM: um trabalho problemático na frente da
    // fila (a mais antiga primeiro) segurava todo pedido novo atrás dele.
    final jobs = _rows(
      page,
    ).where(MobilePrintJobPolicy.shouldAutomaticallyPrint);
    final ordenados = [
      ...jobs.where((j) => !_falhas.containsKey('${j['id']}')),
      ...jobs.where((j) => _falhas.containsKey('${j['id']}')),
    ];
    final semResposta = <String>{};
    for (final job in ordenados) {
      final jobId = '${job['id'] ?? ''}';
      final printer = available['${job['printer'] ?? ''}'];
      final retryAt = _retryAfter[jobId];
      if (jobId.isEmpty || printer == null) continue;
      if (semResposta.contains(printer.id)) continue;
      if (_awaitingConfirmation.contains(jobId)) continue;
      if (retryAt != null && retryAt.isAfter(DateTime.now())) continue;
      // UM trabalho com erro não interrompe o ciclo: antes a exceção subia e
      // nenhum outro trabalho era impresso, ciclo após ciclo.
      try {
        if (!await _claim(jobId)) continue;
        if (!await _printJob(jobId, job, printer)) semResposta.add(printer.id);
      } on ApiException catch (error) {
        if (error.isConnectivity) rethrow;
        _adiar(jobId);
        _lastError = error.message;
      }
    }
  }

  Future<bool> _claim(String jobId) async {
    try {
      await api.post('/print-jobs/$jobId/claim/');
      return true;
    } on ApiException catch (error) {
      if (error.statusCode == 409) return false;
      rethrow;
    }
  }

  Future<void> _loadPrintersIfNeeded(String restaurant) async {
    final loadedAt = _printersLoadedAt;
    if (loadedAt != null &&
        DateTime.now().difference(loadedAt) < const Duration(minutes: 2)) {
      return;
    }
    final page = await api.get(
      '/printers/',
      query: {'restaurant': restaurant, 'is_active': true, 'page_size': 100},
    );
    _printers = _rows(page).map(MobilePrinter.fromJson).toList();
    _printersLoadedAt = DateTime.now();
  }

  Future<void> _confirmPrintedJobs() async {
    for (final jobId in _awaitingConfirmation.toList()) {
      try {
        await _confirmPrintedJob(jobId);
      } on ApiException catch (error) {
        if (error.isConnectivity) return;
        rethrow;
      }
    }
  }

  Future<void> _confirmPrintedJob(String jobId) async {
    await api.post('/print-jobs/$jobId/mark-printed/');
    _awaitingConfirmation.remove(jobId);
    await confirmations.remove(jobId);
  }

  List<Map<String, dynamic>> _rows(Map<String, dynamic> page) {
    final value = page['results'] ?? page['data'];
    if (value is! List) return const [];
    return value.whereType<Map>().map(Map<String, dynamic>.from).toList();
  }

  /// Imprime; devolve `false` quando a IMPRESSORA falhou (para o ciclo pular
  /// os outros trabalhos dela em vez de esperar o tempo limite de cada um).
  Future<bool> _printJob(
    String jobId,
    Map<String, dynamic> job,
    MobilePrinter printer,
  ) async {
    final payload = job['payload'] is Map
        ? Map<String, dynamic>.from(job['payload'] as Map)
        : const <String, dynamic>{};
    final text = '${payload['text_content'] ?? ''}'.trimRight();
    if (text.isEmpty) {
      await api.post(
        '/print-jobs/$jobId/mark-failed/',
        body: {'error': 'Trabalho sem text_content.'},
      );
      return true;
    }
    final barcode = payload['barcode'] is Map
        ? '${(payload['barcode'] as Map)['value'] ?? ''}'
        : '';
    try {
      await writer.write(
        printer,
        encoder.encode(text: text, barcode: barcode, escPos: printer.isEscPos),
      );
      _printedCount += 1;
      _retryAfter.remove(jobId);
      _falhas.remove(jobId);
      _awaitingConfirmation.add(jobId);
      await confirmations.add(jobId);
      await _confirmPrintedJob(jobId);
    } catch (error) {
      if (_awaitingConfirmation.contains(jobId)) {
        _lastError = 'O papel saiu, mas a confirmação ficou pendente: $error';
        return true;
      }
      _adiar(jobId);
      _lastError = '$error';
      try {
        await api.post('/print-jobs/$jobId/release/');
      } catch (_) {
        // A reserva expira sozinha no servidor; não pode travar a fila.
      }
      return false;
    }
    return true;
  }

  /// Trabalho com falha recebe espera crescente até 60 s e vai para o fim da
  /// fila, sem segurar as comandas novas enquanto a impressora se recupera.
  void _adiar(String jobId) {
    final vezes = (_falhas[jobId] ?? 0) + 1;
    _falhas[jobId] = vezes;
    const esperasSegundos = [3, 8, 15, 30, 60];
    final segundos = esperasSegundos[(vezes - 1).clamp(0, 4)];
    _retryAfter[jobId] = DateTime.now().add(Duration(seconds: segundos));
  }
}
