import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

abstract interface class PrintAttemptStorage {
  Future<Map<String, int>> load();
  Future<void> save(String jobId, int attempts);
  Future<void> remove(String jobId);
}

class FilePrintAttemptStore implements PrintAttemptStorage {
  FilePrintAttemptStore({this.testFile});

  final File? testFile;
  File? _file;
  Map<String, int>? _attempts;
  Future<void> _writeTail = Future.value();

  @override
  Future<Map<String, int>> load() async {
    final current = _attempts;
    if (current != null) return Map.of(current);
    try {
      final file = await _resolveFile();
      if (!await file.exists()) return _remember({});
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! Map) return _remember({});
      return _remember({
        for (final entry in decoded.entries)
          if (int.tryParse('${entry.value}') case final int count)
            '${entry.key}': count < 0 ? 0 : count,
      });
    } catch (_) {
      return _remember({});
    }
  }

  @override
  Future<void> save(String jobId, int attempts) async {
    final current = await load();
    current[jobId] = attempts < 0 ? 0 : attempts;
    _attempts = current;
    await _save();
  }

  @override
  Future<void> remove(String jobId) async {
    final current = await load();
    if (current.remove(jobId) == null) return;
    _attempts = current;
    await _save();
  }

  Map<String, int> _remember(Map<String, int> value) {
    _attempts = value;
    return Map.of(value);
  }

  Future<File> _resolveFile() async {
    final current = _file;
    if (current != null) return current;
    final directory = await getApplicationSupportDirectory();
    return _file =
        testFile ??
        File('${directory.path}${Platform.pathSeparator}print_attempts.json');
  }

  Future<void> _save() {
    final operation = _writeTail.then((_) async {
      final file = await _resolveFile();
      await file.parent.create(recursive: true);
      final temporary = File('${file.path}.tmp');
      await temporary.writeAsString(jsonEncode(_attempts), flush: true);
      await temporary.rename(file.path);
    });
    _writeTail = operation.catchError((_) {});
    return operation;
  }
}
