import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import 'app_paths.dart';

/// Preferências locais do terminal (tema, timeouts e impressão).
///
/// Um arquivo JSON evita mais uma dependência nativa e se comporta igual em
/// Windows e Linux. As gravações são serializadas e atômicas — escreve em um
/// arquivo temporário e renomeia — para que uma queda de energia no meio da
/// escrita não deixe um JSON truncado que impediria o próximo boot.
///
/// Vínculos de periféricos e o pareamento do Caixa Principal continuam nos
/// seus próprios bancos, que já têm restrições de unicidade.
class LocalPreferences {
  LocalPreferences({File? file}) : _file = file ?? AppPaths.dataFile(_fileName);

  static const _fileName = 'preferences.json';
  static const _themeKey = 'theme_mode';
  static const _commandTimeoutKey = 'scale_command_timeout_seconds';
  static const _stabilityToleranceKey = 'scale_stability_tolerance_kg';
  static const _audibleAlertsKey = 'scale_audible_alerts';
  static const _autoPrintKey = 'scale_auto_print';
  static const _showCatalogKey = 'scale_show_catalog';
  static const _apiBaseUrlOverrideKey = 'api_base_url_override';
  static const _serialPortOverridesKey = 'serial_port_overrides';
  static const _masterPrinterIdKey = 'master_printer_id';
  static const _servedAsPrincipalKey = 'served_as_principal';

  final File _file;
  Map<String, dynamic> _values = const {};
  bool _loaded = false;
  Future<void> _writeTail = Future.value();

  /// Lê o arquivo uma única vez. Um JSON corrompido volta ao padrão em vez de
  /// impedir a abertura do PDV.
  Future<void> load() async {
    if (_loaded) return;
    _loaded = true;
    try {
      if (!await _file.exists()) return;
      final decoded = jsonDecode(await _file.readAsString());
      if (decoded is Map) _values = Map<String, dynamic>.from(decoded);
    } catch (_) {
      _values = const {};
    }
  }

  ThemeMode get themeMode => switch ('${_values[_themeKey] ?? ''}') {
    'dark' => ThemeMode.dark,
    'light' => ThemeMode.light,
    'system' => ThemeMode.system,
    _ => ThemeMode.dark,
  };

  Future<void> setThemeMode(ThemeMode mode) => _write(_themeKey, mode.name);

  /// Tempo máximo aguardando a leitura da comanda antes de cancelar a operação
  /// temporária e voltar ao estado inicial.
  Duration get commandTimeout => Duration(
    seconds: _int(_commandTimeoutKey, fallback: 45, min: 10, max: 600),
  );

  Future<void> setCommandTimeout(Duration value) =>
      _write(_commandTimeoutKey, value.inSeconds.clamp(10, 600));

  /// Oscilação tolerada entre leituras para considerar o peso estável.
  double get stabilityToleranceKg =>
      _double(_stabilityToleranceKey, fallback: 0.002, min: 0.001, max: 0.5);

  Future<void> setStabilityToleranceKg(double value) =>
      _write(_stabilityToleranceKey, value.clamp(0.001, 0.5));

  bool get audibleAlerts => _values[_audibleAlertsKey] as bool? ?? true;

  Future<void> setAudibleAlerts(bool value) => _write(_audibleAlertsKey, value);

  /// Imprime o cupom automaticamente ao concluir o pedido da balança.
  bool get autoPrint => _values[_autoPrintKey] as bool? ?? true;

  Future<void> setAutoPrint(bool value) => _write(_autoPrintKey, value);

  /// Mostra a coluna de cardápio (extras) na Balança Rápida.
  ///
  /// Terminais que só pesam e leem a comanda — sem vender extras do balcão —
  /// preferem esconder essa coluna, que sobra vazia no meio da tela.
  bool get showScaleCatalog => _values[_showCatalogKey] as bool? ?? true;

  Future<void> setShowScaleCatalog(bool value) =>
      _write(_showCatalogKey, value);

  /// URL da API definida manualmente na tela de login (sobrescreve o que veio
  /// de --dart-define/.env — ver `AppConfig.load`). `null`/vazio significa
  /// "sem override, usa a configuração padrão do build".
  String? get apiBaseUrlOverride {
    final value = _values[_apiBaseUrlOverrideKey] as String?;
    return (value == null || value.trim().isEmpty) ? null : value.trim();
  }

  Future<void> setApiBaseUrlOverride(String? value) => _write(
    _apiBaseUrlOverrideKey,
    (value == null || value.trim().isEmpty) ? null : value.trim(),
  );

  /// Impressora fixada pelo caixa para o recibo de pagamento e o recibo do
  /// cliente. `null` significa "sem master, pergunta qual impressora usar"
  /// — o comportamento de hoje.
  String? get masterPrinterId {
    final value = _values[_masterPrinterIdKey] as String?;
    return (value == null || value.trim().isEmpty) ? null : value.trim();
  }

  Future<void> setMasterPrinterId(String? value) => _write(
    _masterPrinterIdKey,
    (value == null || value.trim().isEmpty) ? null : value.trim(),
  );

  /// Este terminal já servia a fila de impressão como Caixa Principal na
  /// última vez que operou?
  ///
  /// Distingue as duas partidas que, do lado do agente, são idênticas: um
  /// principal que reiniciou (o que estava pendente no servidor é dele, e
  /// deve sair) e um terminal que acabou de trocar de papel (o que estava
  /// pendente é do principal anterior, e sair de novo é imprimir duas vezes).
  /// Precisa sobreviver ao fechamento do PDV, por isso mora aqui e não na
  /// memória do agente.
  bool get servedAsPrincipal => _values[_servedAsPrincipalKey] as bool? ?? false;

  Future<void> setServedAsPrincipal(bool value) =>
      _write(_servedAsPrincipalKey, value);

  /// Porta guardada por versões antigas para este equipamento neste terminal.
  ///
  /// O override existiu para o caso de o mesmo equipamento receber caminhos
  /// diferentes em cada máquina, mas criava um problema pior: a porta salva
  /// aqui envelhecia em relação ao cadastro e a impressão real abria um
  /// dispositivo diferente do que a tela mostrava. Hoje quem descreve o
  /// equipamento — protocolo, IP e porta, caminho serial — é sempre o
  /// cadastro. Isto sobrevive apenas para limpar o que ficou gravado.
  String? legacySerialPortOverride({
    required String kind,
    required String deviceId,
  }) {
    final overrides = _values[_serialPortOverridesKey];
    if (overrides is! Map) return null;
    final value = overrides['$kind:$deviceId'];
    final normalized = '${value ?? ''}'.trim();
    return normalized.isEmpty ? null : normalized;
  }

  Future<void> clearSerialPortOverride({
    required String kind,
    required String deviceId,
  }) {
    final current = _values[_serialPortOverridesKey];
    if (current is! Map) return Future.value();
    final overrides = Map<String, dynamic>.from(current);
    if (overrides.remove('$kind:$deviceId') == null) return Future.value();
    return _write(_serialPortOverridesKey, overrides);
  }

  int _int(
    String key, {
    required int fallback,
    required int min,
    required int max,
  }) {
    final raw = _values[key];
    final value = raw is num ? raw.toInt() : int.tryParse('$raw');
    if (value == null) return fallback;
    return value.clamp(min, max);
  }

  double _double(
    String key, {
    required double fallback,
    required double min,
    required double max,
  }) {
    final raw = _values[key];
    final value = raw is num ? raw.toDouble() : double.tryParse('$raw');
    if (value == null || value.isNaN) return fallback;
    return value.clamp(min, max);
  }

  Future<void> _write(String key, Object? value) {
    _values = {..._values, key: value};
    final snapshot = Map<String, dynamic>.from(_values);
    // As gravações são encadeadas para que duas mudanças rápidas não disputem
    // o mesmo arquivo e produzam um estado misturado.
    return _writeTail = _writeTail.then((_) => _flush(snapshot));
  }

  Future<void> _flush(Map<String, dynamic> snapshot) async {
    try {
      await _file.parent.create(recursive: true);
      final temporary = File('${_file.path}.tmp');
      await temporary.writeAsString(jsonEncode(snapshot), flush: true);
      await temporary.rename(_file.path);
    } catch (_) {
      // Preferências são conveniência: um disco cheio ou somente leitura não
      // pode derrubar o caixa. O valor continua válido em memória.
    }
  }
}
