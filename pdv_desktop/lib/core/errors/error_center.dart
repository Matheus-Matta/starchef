import 'dart:async';

import 'package:flutter/foundation.dart';

import '../logging/app_logger.dart';
import '../network/api_exception.dart';
import 'app_error.dart';

/// Central única de notificações do aplicativo.
///
/// Duas listas, com propósitos diferentes — e a distinção é a regra principal:
///
/// **[visible]** é o que INTERROMPE a tela, e só recebe [AppErrorSeverity.failure].
/// Sucesso e aviso deixaram de aparecer sozinhos porque o custo deles é alto no
/// lugar errado: um "venda concluída" cobrindo o teclado no instante em que o
/// operador começa o próximo pedido atrapalha justamente quem acertou.
///
/// **[history]** guarda TUDO, do mais novo para o mais velho, e é o que o sino
/// da barra superior mostra. Quem quiser conferir o que passou, confere quando
/// quiser — sem nada pular na frente.
///
/// O histórico tem teto de [maximumHistory]: ao chegar a 21, a mais antiga sai.
/// Um PDV fica aberto o turno inteiro, e sem teto a lista cresceria até o fim
/// do expediente.
///
/// Nada é descartado em silêncio: mesmo o que não aparece na tela já foi para o
/// log antes de entrar aqui.
class ErrorCenter extends ChangeNotifier {
  ErrorCenter({
    AppLogger? logger,
    this.maximumVisible = 3,
    this.maximumHistory = 20,
  }) : _logger = logger ?? AppLogger.instance;

  final AppLogger _logger;
  final int maximumVisible;

  /// Quantas notificações o sino guarda. A de número 21 empurra a mais antiga.
  final int maximumHistory;

  final List<AppError> _visible = [];
  final List<AppError> _history = [];
  final Map<AppError, Timer> _dismissTimers = {};
  int _lastSeenCount = 0;

  /// Tempo padrão em tela de qualquer alerta que não define o próprio
  /// [AppError.autoDismissAfter] — falha, aviso ou confirmação.
  static const defaultAutoDismissAfter = Duration(seconds: 2);

  List<AppError> get visible => List.unmodifiable(_visible);
  bool get hasErrors => _visible.isNotEmpty;

  /// Tudo que foi notificado, do mais novo para o mais velho.
  List<AppError> get history => List.unmodifiable(_history);

  /// Quantas chegaram desde a última vez que o operador abriu o sino.
  ///
  /// Contagem, e não marca por item: o que o operador quer saber é "apareceu
  /// coisa nova?", e abrir a lista responde isso por inteiro.
  int get unreadCount => _history.length - _lastSeenCount < 0
      ? 0
      : _history.length - _lastSeenCount;

  bool get hasUnread => unreadCount > 0;

  /// Chamado quando o sino é aberto: o que estava novo deixa de estar.
  void markAllSeen() {
    if (_lastSeenCount == _history.length) return;
    _lastSeenCount = _history.length;
    notifyListeners();
  }

  /// Esvazia o histórico do sino. Não mexe no que está na tela.
  void clearHistory() {
    if (_history.isEmpty) return;
    _history.clear();
    _lastSeenCount = 0;
    notifyListeners();
  }

  /// Publica um erro e devolve a instância exibida.
  AppError report(AppError error) {
    _logger.log(
      switch (error.severity) {
        AppErrorSeverity.failure => LogLevel.error,
        AppErrorSeverity.warning => LogLevel.warning,
        AppErrorSeverity.info => LogLevel.info,
        AppErrorSeverity.success => LogLevel.info,
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
    bool mesmaNatureza(AppError item) => key != null
        ? item.dedupeKey == key
        : item.title == error.title && item.message == error.message;

    _removeWhere(mesmaNatureza);
    // O dedupe vale para o histórico também. Sem isso, dez tentativas sem rede
    // viravam UM alerta na tela e DEZ linhas no sino — enchendo metade do teto
    // de 20 com a mesma frase repetida, que é exatamente o que o dedupe existe
    // para evitar.
    _history.removeWhere(mesmaNatureza);
    if (_lastSeenCount > _history.length) _lastSeenCount = _history.length;

    // O histórico recebe TUDO — é o registro do turno, e um sucesso engolido
    // aqui é um sucesso que ninguém consegue conferir depois.
    _history.insert(0, error);
    while (_history.length > maximumHistory) {
      _history.removeLast();
      // O ponteiro de "já visto" acompanha a lista encolhendo; sem isso, uma
      // remoção por teto faria a contagem de novas ficar negativa e o sino
      // mostraria número errado.
      if (_lastSeenCount > _history.length) _lastSeenCount = _history.length;
    }

    // A tela recebe só o que exige reação AGORA.
    if (error.severity != AppErrorSeverity.failure) {
      notifyListeners();
      return error;
    }

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
