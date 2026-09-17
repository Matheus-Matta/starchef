import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

abstract interface class PrintConfirmationStorage {
  Future<Set<String>> load();
  Future<void> add(String jobId);
  Future<void> remove(String jobId);
}

class FilePrintConfirmationStore implements PrintConfirmationStorage {
  FilePrintConfirmationStore({this.testFile});

  final File? testFile;
  File? _file;
  Set<String>? _ids;
  Future<void> _writeTail = Future.value();

  @override
  Future<Set<String>> load() async {
    final current = _ids;
    if (current != null) return Set.of(current);
    try {
      final file = await _resolveFile();
      if (!await file.exists()) return _remember(<String>{});
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! List) return _remember(<String>{});
      return _remember(decoded.map((item) => '$item').toSet());
    } catch (_) {
      return _remember(<String>{});
    }
  }

  @override
  Future<void> add(String jobId) async {
    final ids = await load();
    if (!ids.add(jobId)) return;
    _ids = ids;
    await _save();
  }

  @override
  Future<void> remove(String jobId) async {
    final ids = await load();
    if (!ids.remove(jobId)) return;
    _ids = ids;
    await _save();
  }

  Set<String> _remember(Set<String> value) {
    _ids = value;
    return Set.of(value);
  }

  Future<File> _resolveFile() async {
    final current = _file;
    if (current != null) return current;
    final directory = await getApplicationSupportDirectory();
    return _file =
        testFile ??
        File(
          '${directory.path}${Platform.pathSeparator}printed_confirmations.json',
        );
  }

  Future<void> _save() {
    final operation = _writeTail.then((_) async {
      final file = await _resolveFile();
      await file.parent.create(recursive: true);
      final temporary = File('${file.path}.tmp');
      await temporary.writeAsString(jsonEncode(_ids!.toList()), flush: true);
      await temporary.rename(file.path);
    });
    _writeTail = operation.catchError((_) {});
    return operation;
  }
}
