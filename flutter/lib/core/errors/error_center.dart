import 'package:flutter/foundation.dart';

import '../logging/app_logger.dart';
import '../network/api_exception.dart';
import 'app_error.dart';

/// Fila única de erros visíveis do aplicativo.
///
/// Todo erro reportado aqui aparece com botão de fechar e só some quando o
/// operador o dispensa (ou quando o mesmo erro é substituído por uma repetição
/// idêntica). Nada é descartado silenciosamente: mesmo quando a interface não
/// consegue exibir, o detalhe técnico já foi para o log.
class ErrorCenter extends ChangeNotifier {
  ErrorCenter({AppLogger? logger, this.maximumVisible = 3})
    : _logger = logger ?? AppLogger.instance;

  final AppLogger _logger;
  final int maximumVisible;
  final List<AppError> _visible = [];

  List<AppError> get visible => List.unmodifiable(_visible);
  bool get hasErrors => _visible.isNotEmpty;

  /// Publica um erro e devolve a instância exibida.
  AppError report(AppError error) {
    _logger.log(
      switch (error.severity) {
        AppErrorSeverity.failure => LogLevel.error,
        AppErrorSeverity.warning => LogLevel.warning,
        AppErrorSeverity.info => LogLevel.info,
      },
      'ui_error',
      data: {
        'title': error.title,
        'message': error.message,
        'code': error.code,
        'origin': error.origin.name,
        'action': error.recommendedAction,
        'details': error.technicalDetails,
      },
    );

    // Repetir a mesma falha (um retry que falha de novo) apenas renova a
    // mensagem existente em vez de empilhar cópias. Erros com `dedupeKey`
    // agrupam por natureza: dez chamadas sem rede produzem um aviso, não dez.
    final key = error.dedupeKey;
    _visible.removeWhere(
      (item) => key != null
          ? item.dedupeKey == key
          : item.title == error.title && item.message == error.message,
    );
    _visible.insert(0, error);
    while (_visible.length > maximumVisible) {
      _visible.removeLast();
    }
    notifyListeners();
    if (error.autoDismissAfter case final delay?) {
      Future.delayed(delay, () => dismiss(error));
    }
    return error;
  }

  /// Atalho para falhas da API preservando a mensagem do backend.
  AppError reportApi(
    ApiException exception, {
    String? title,
    String? recommendedAction,
  }) => report(
    AppError.fromApi(
      exception,
      title: title,
      recommendedAction: recommendedAction,
    ),
  );

  /// Atalho para exceções inesperadas, sem stack trace na tela.
  AppError reportUnexpected(
    Object error, {
    String? title,
    StackTrace? stackTrace,
    AppErrorOrigin origin = AppErrorOrigin.application,
  }) => report(
    AppError.unexpected(
      error,
      title: title,
      stackTrace: stackTrace,
      origin: origin,
    ),
  );

  /// Fecha um alerta específico — o que o botão `X` aciona.
  void dismiss(AppError error) {
    if (_visible.remove(error)) notifyListeners();
  }

  /// Fecha os alertas de uma natureza que deixou de existir.
  ///
  /// Usado quando a própria condição se resolve — a conexão voltar, por
  /// exemplo —, para o operador não precisar dispensar um aviso obsoleto.
  void dismissByKey(String dedupeKey) {
    final removed = _visible.length;
    _visible.removeWhere((item) => item.dedupeKey == dedupeKey);
    if (_visible.length != removed) notifyListeners();
  }

  void dismissAll() {
    if (_visible.isEmpty) return;
    _visible.clear();
    notifyListeners();
  }
}
