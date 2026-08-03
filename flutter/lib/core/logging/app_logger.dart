import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';

import '../storage/app_paths.dart';

enum LogLevel { debug, info, warning, error }

/// Log estruturado em JSON por linha, gravado ao lado dos dados do terminal.
///
/// O operador nunca vê estas linhas; elas existem para diagnosticar uma venda
/// específica depois do fato. A gravação é encadeada e tolerante a falhas: um
/// disco cheio degrada para somente console, nunca derruba o caixa.
class AppLogger {
  AppLogger._();

  static final AppLogger instance = AppLogger._();

  static const _maximumBytes = 2 * 1024 * 1024;

  File? _file;
  Future<void> _writeTail = Future.value();

  void debug(String event, {Map<String, Object?>? data}) =>
      log(LogLevel.debug, event, data: data);

  void info(String event, {Map<String, Object?>? data}) =>
      log(LogLevel.info, event, data: data);

  void warning(String event, {Map<String, Object?>? data}) =>
      log(LogLevel.warning, event, data: data);

  void error(
    String event, {
    Map<String, Object?>? data,
    Object? cause,
    StackTrace? stackTrace,
  }) => log(
    LogLevel.error,
    event,
    data: {
      ...?data,
      if (cause != null) 'cause': '$cause',
      if (stackTrace != null) 'stack': '$stackTrace',
    },
  );

  void log(LogLevel level, String event, {Map<String, Object?>? data}) {
    final entry = <String, Object?>{
      'at': DateTime.now().toUtc().toIso8601String(),
      'level': level.name,
      'event': event,
      if (data != null && data.isNotEmpty) 'data': _sanitize(data),
    };
    late final String line;
    try {
      line = jsonEncode(entry);
    } catch (_) {
      line = jsonEncode({
        'at': entry['at'],
        'level': level.name,
        'event': event,
        'data': {'note': 'payload não serializável'},
      });
    }
    if (kDebugMode) debugPrint(line);
    _writeTail = _writeTail.then((_) => _append(line));
  }

  /// Remove valores que não devem chegar ao disco em texto puro.
  static Map<String, Object?> _sanitize(Map<String, Object?> data) {
    const secretKeys = {
      'password',
      'cash_password',
      'access',
      'refresh',
      'token',
      'access_token',
      'refresh_token',
      'authorization',
      'pairing_secret',
    };
    return {
      for (final entry in data.entries)
        entry.key: secretKeys.contains(entry.key.toLowerCase())
            ? '***'
            : entry.value,
    };
  }

  Future<void> _append(String line) async {
    try {
      final file = _file ??= AppPaths.dataFile('pdv.log');
      await file.parent.create(recursive: true);
      if (await file.exists() && await file.length() > _maximumBytes) {
        // Uma única rotação preserva o histórico recente sem crescer sem fim.
        await file.rename('${file.path}.1');
        _file = file;
      }
      await file.writeAsString(
        '$line\n',
        mode: FileMode.append,
        flush: false,
      );
    } catch (_) {
      // Sem log em disco o aplicativo continua operando normalmente.
    }
  }
}
