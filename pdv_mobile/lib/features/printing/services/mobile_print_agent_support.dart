part of 'mobile_print_agent.dart';

extension _MobilePrintAgentSupport on MobilePrintAgent {
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
    for (final job in _rows(page)) {
      if (!MobilePrintJobPolicy.shouldAutomaticallyPrint(job)) continue;
      final jobId = '${job['id'] ?? ''}';
      final printer = available['${job['printer'] ?? ''}'];
      final retryAt = _retryAfter[jobId];
      if (jobId.isEmpty || printer == null) continue;
      if (_awaitingConfirmation.contains(jobId)) continue;
      if (retryAt != null && retryAt.isAfter(DateTime.now())) continue;
      if (!await _claim(jobId)) continue;
      await _printJob(jobId, job, printer);
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
}
