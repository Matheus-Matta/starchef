import 'dart:async';
import 'dart:convert';
import 'dart:io';

class OfflineStore {
  OfflineStore({File? file}) : _file = file ?? _defaultFile();

  final File _file;
  Future<void> _lock = Future.value();
  Map<String, dynamic>? _memory;
  static const _maxCacheEntries = 300;

  static File _defaultFile() {
    final configured = Platform.environment['LOCALAPPDATA'];
    final base = configured == null || configured.trim().isEmpty
        ? Directory.systemTemp.path
        : configured;
    return File(
      '$base${Platform.pathSeparator}StarChef'
      '${Platform.pathSeparator}offline_data.json',
    );
  }

  Future<Map<String, dynamic>?> cached(String key) async {
    final data = await _read();
    final value = (data['cache'] as Map<String, dynamic>? ?? const {})[key];
    return value is Map ? Map<String, dynamic>.from(value) : null;
  }

  Future<void> cache(String key, Map<String, dynamic> value) async {
    // Respostas de polling podem se repetir por horas. Evita regravar todo o
    // arquivo offline quando o servidor não trouxe nenhuma alteração.
    final current = await cached(key);
    if (current != null && jsonEncode(current) == jsonEncode(value)) return;
    await _mutate((data) {
      final cache = Map<String, dynamic>.from(
        data['cache'] as Map? ?? const {},
      );
      cache[key] = value;
      while (cache.length > _maxCacheEntries) {
        cache.remove(cache.keys.first);
      }
      data['cache'] = cache;
    });
  }

  Future<List<Map<String, dynamic>>> pending() async {
    final data = await _read();
    return ((data['outbox'] as List?) ?? const [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  Future<void> enqueue(Map<String, dynamic> request) => _mutate((data) {
    final outbox = List<dynamic>.from(data['outbox'] as List? ?? const []);
    outbox.add(request);
    data['outbox'] = outbox;
  });

  Future<void> remove(String queueId) => _mutate((data) {
    final outbox = List<dynamic>.from(data['outbox'] as List? ?? const []);
    outbox.removeWhere(
      (item) => item is Map && '${item['queue_id']}' == queueId,
    );
    data['outbox'] = outbox;
  });

  Future<void> replaceTemporaryId(String temporaryId, String realId) =>
      _mutate((data) {
        final replaced =
            jsonDecode(jsonEncode(data).replaceAll(temporaryId, realId))
                as Map<String, dynamic>;
        data
          ..clear()
          ..addAll(replaced);
      });

  Future<void> applyOptimistic({
    required String path,
    required String method,
    required Map<String, dynamic> value,
  }) => _mutate((data) {
    final cache = Map<String, dynamic>.from(data['cache'] as Map? ?? const {});
    final cleanPath = path.split('?').first;
    final segments = cleanPath
        .split('/')
        .where((part) => part.isNotEmpty)
        .toList();
    final entityId = method == 'POST'
        ? '${value['id'] ?? ''}'
        : (segments.isEmpty ? '' : segments.last);

    for (final entry in cache.entries.toList()) {
      if (entry.value is! Map) continue;
      final response = Map<String, dynamic>.from(entry.value as Map);
      final results = response['results'];
      if (results is! List) continue;
      final list = results
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
      final index = list.indexWhere((item) => '${item['id']}' == entityId);
      if (method == 'DELETE' && index >= 0) {
        list.removeAt(index);
      } else if (method == 'PATCH' && index >= 0) {
        list[index] = {...list[index], ...value};
      } else if (method == 'POST' &&
          entry.key.contains(cleanPath) &&
          value['id'] != null) {
        list.insert(0, value);
      }
      response['results'] = list;
      cache[entry.key] = response;
    }
    data['cache'] = cache;
  });

  Future<Map<String, dynamic>> _read() async {
    if (_memory != null) return _memory!;
    try {
      if (!await _file.exists()) {
        return _memory = _emptyData();
      }
      final decoded = jsonDecode(await _file.readAsString());
      return _memory = decoded is Map<String, dynamic> ? decoded : _emptyData();
    } catch (_) {
      return _memory = _emptyData();
    }
  }

  Map<String, dynamic> _emptyData() => {
    'cache': <String, dynamic>{},
    'outbox': <dynamic>[],
  };

  Future<void> _mutate(void Function(Map<String, dynamic>) operation) {
    final completer = Completer<void>();
    _lock = _lock
        .then((_) async {
          final data = await _read();
          operation(data);
          await _file.parent.create(recursive: true);
          final temporary = File('${_file.path}.tmp');
          await temporary.writeAsString(jsonEncode(data), flush: true);
          if (await _file.exists()) await _file.delete();
          await temporary.rename(_file.path);
          completer.complete();
        })
        .catchError((Object error, StackTrace stack) {
          if (!completer.isCompleted) completer.completeError(error, stack);
        });
    return completer.future;
  }
}
