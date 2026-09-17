part of 'mobile_print_agent.dart';

extension _MobilePrintAgentSupport on MobilePrintAgent {
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
