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

  /// Espera o que já foi enfileirado chegar ao disco.
  ///
  /// As escritas são encadeadas e disparadas sem espera (o log nunca segura o
  /// caixa). Isso torna o arquivo impossível de conferir em teste sem um ponto
  /// de sincronização — e a máscara de segredos precisa ser conferível.
  Future<void> flush() => _writeTail;

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

  static const _secretKeys = {
    'password',
    'cash_password',
    'access',
    'refresh',
    'token',
    'access_token',
    'refresh_token',
    'authorization',
    'pairing_secret',
    'csc_token',
    'certificate_password',
  };

  /// Remove valores que não devem chegar ao disco em texto puro.
  ///
  /// Desce nos mapas e listas aninhados. A máscara olhava só o primeiro nível,
  /// e o log deste PDV registra corpo de requisição inteiro em vários pontos
  /// (`causa: '$error'`, `data: {...body}`) — um `token` dentro de
  /// `{'origin': {...}}` ou de uma lista de operações da fila passava direto
  /// para o disco em texto puro.
  static Map<String, Object?> _sanitize(Map<String, Object?> data) => {
    for (final entry in data.entries)
      entry.key: _sanitizeValue(entry.key, entry.value),
  };

  static Object? _sanitizeValue(String key, Object? value) {
    if (_secretKeys.contains(key.toLowerCase())) return '***';
    if (value is Map) {
      return {
        for (final entry in value.entries)
          '${entry.key}': _sanitizeValue('${entry.key}', entry.value),
      };
    }
    if (value is Iterable) {
      // A chave do item de uma lista é a da própria lista: `tokens: [...]`
      // já foi mascarado acima; aqui só se desce em busca de mapas dentro.
      return [for (final item in value) _sanitizeValue(key, item)];
    }
    return value;
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
      await file.writeAsString('$line\n', mode: FileMode.append, flush: false);
    } catch (_) {
      // Sem log em disco o aplicativo continua operando normalmente.
    }
  }
}
