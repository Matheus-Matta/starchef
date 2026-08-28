import 'dart:async';

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
  final Map<AppError, Timer> _dismissTimers = {};

  /// Tempo padrão em tela de qualquer alerta que não define o próprio
  /// [AppError.autoDismissAfter] — falha, aviso ou confirmação.
  static const defaultAutoDismissAfter = Duration(seconds: 2);

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
    _removeWhere(
      (item) => key != null
          ? item.dedupeKey == key
          : item.title == error.title && item.message == error.message,
    );
    _visible.insert(0, error);
    while (_visible.length > maximumVisible) {
      _cancelTimer(_visible.removeLast());
    }
    notifyListeners();
    // Todo alerta some sozinho depois de um tempo — inclusive falha e aviso.
    // O operador ainda pode fechar antes pelo `X`; o que muda é que agora
    // nada fica preso na tela esperando um clique que talvez nunca venha.
    // Guardado como `Timer` (não `Future.delayed` solto) para poder ser
    // cancelado se o alerta sair da lista antes por outro caminho — sem
    // isso, o timer disparava depois do teste/tela já ter descartado o
    // `ErrorCenter`, e em teste de widget isso quebra a verificação de que
    // nenhum timer fica pendente.
    final delay = error.autoDismissAfter ?? defaultAutoDismissAfter;
    _dismissTimers[error] = Timer(delay, () => dismiss(error));
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

  /// Fecha um alerta específico — o que o botão `X` aciona, e também o que o
  /// timer de auto-dismiss chama sozinho.
  void dismiss(AppError error) {
    _cancelTimer(error);
    if (_visible.remove(error)) notifyListeners();
  }

  /// Fecha os alertas de uma natureza que deixou de existir.
  ///
  /// Usado quando a própria condição se resolve — a conexão voltar, por
  /// exemplo —, para o operador não precisar dispensar um aviso obsoleto.
  void dismissByKey(String dedupeKey) {
    if (_removeWhere((item) => item.dedupeKey == dedupeKey)) {
      notifyListeners();
    }
  }

  void dismissAll() {
    if (_visible.isEmpty) return;
    for (final error in _visible) {
      _cancelTimer(error);
    }
    _visible.clear();
    notifyListeners();
  }

  /// Remove da lista visível e cancela o timer de quem sai — sem isso, um
  /// alerta descartado por dedupe/limite continuaria disparando `dismiss` no
  /// tempo certo dele, só que já sem efeito nenhum (e, em teste de widget,
  /// como um timer pendente depois do fim do teste).
  bool _removeWhere(bool Function(AppError item) test) {
    var removedAny = false;
    _visible.removeWhere((item) {
      final matches = test(item);
      if (matches) {
        _cancelTimer(item);
        removedAny = true;
      }
      return matches;
    });
    return removedAny;
  }

  AppError _cancelTimer(AppError error) {
    _dismissTimers.remove(error)?.cancel();
    return error;
  }

  @override
  void dispose() {
    for (final timer in _dismissTimers.values) {
      timer.cancel();
    }
    _dismissTimers.clear();
    super.dispose();
  }
}
