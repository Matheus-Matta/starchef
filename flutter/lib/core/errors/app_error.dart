import '../network/api_exception.dart';

/// Gravidade usada para escolher a apresentação e a urgência do alerta.
enum AppErrorSeverity { info, warning, failure }

/// Origem do problema, usada no texto de apoio e nos logs.
enum AppErrorOrigin {
  /// Regra ou validação retornada pela API.
  api,

  /// Falha de rede, timeout ou servidor inacessível.
  network,

  /// Balança, leitor ou impressora.
  peripheral,

  /// Caixa Principal / Caixa Cliente na rede local.
  localNetwork,

  /// Falha do próprio aplicativo.
  application,
}

/// Erro pronto para exibição, sem stack trace para o operador.
///
/// A mensagem do backend é preservada literalmente em [message] — o requisito
/// é que uma inconsistência de caixa apareça fiel ao que o servidor respondeu.
/// Detalhes técnicos ficam em [technicalDetails], visíveis apenas sob demanda.
class AppError {
  AppError({
    required this.title,
    required this.message,
    this.code,
    this.origin = AppErrorOrigin.application,
    this.severity = AppErrorSeverity.failure,
    this.recommendedAction,
    this.technicalDetails,
    this.dedupeKey,
    this.autoDismissAfter,
    DateTime? occurredAt,
  }) : occurredAt = occurredAt ?? DateTime.now();

  final String title;
  final String message;
  final String? code;
  final AppErrorOrigin origin;
  final AppErrorSeverity severity;
  final String? recommendedAction;
  final String? technicalDetails;
  final DateTime occurredAt;

  /// Agrupa ocorrências da mesma natureza em um único alerta.
  ///
  /// Sem isso, cada requisição feita sem rede empilharia um cartão novo e
  /// enterraria a tela do operador. Um erro com a mesma chave substitui o
  /// anterior em vez de somar.
  final String? dedupeKey;

  /// Some sozinho depois desse tempo, sem exigir o `X` do operador.
  ///
  /// `null` aqui não significa "para sempre": o [ErrorCenter] aplica
  /// `ErrorCenter.defaultAutoDismissAfter` (2s) para qualquer alerta —
  /// falha, aviso ou confirmação — que não definir o próprio tempo. Só
  /// preencha isto quando UM alerta específico precisar de um tempo
  /// diferente do padrão.
  final Duration? autoDismissAfter;

  /// Converte uma falha da API preservando a mensagem exata do backend.
  factory AppError.fromApi(
    ApiException exception, {
    String? title,
    String? recommendedAction,
  }) {
    final status = exception.statusCode;
    if (exception.isConnectivity) {
      return AppError(
        title: title ?? 'Sem conexão com o servidor',
        message: exception.message,
        origin: AppErrorOrigin.network,
        // Ficar sem rede é um estado esperado neste PDV, não uma falha do
        // operador: o aviso existe para explicar o que não foi concluído.
        severity: AppErrorSeverity.warning,
        recommendedAction:
            'As operações compatíveis seguem na fila local e sobem sozinhas '
            'quando a conexão voltar.',
        technicalDetails: 'ApiException(connectivity)',
        dedupeKey: 'connectivity',
      );
    }
    return AppError(
      title: title ?? _titleForStatus(status),
      message: exception.message,
      code: status == null ? null : 'HTTP $status',
      origin: status == null ? AppErrorOrigin.network : AppErrorOrigin.api,
      recommendedAction: recommendedAction ?? _actionForStatus(status),
      technicalDetails: 'ApiException(statusCode: $status)',
    );
  }

  /// Converte qualquer exceção inesperada sem expor o stack trace na tela.
  factory AppError.unexpected(
    Object error, {
    String? title,
    StackTrace? stackTrace,
    AppErrorOrigin origin = AppErrorOrigin.application,
  }) => AppError(
    title: title ?? 'Ocorreu um erro inesperado',
    message:
        'A operação não pôde ser concluída. Tente novamente; se o problema '
        'continuar, informe o suporte com o horário desta mensagem.',
    origin: origin,
    recommendedAction: 'Repita a operação e confira o resultado.',
    technicalDetails: stackTrace == null
        ? '$error'
        : '$error\n\n$stackTrace',
  );

  /// Rótulo legível da origem, usado no rodapé do alerta.
  String get originLabel => switch (origin) {
    AppErrorOrigin.api => 'Servidor',
    AppErrorOrigin.network => 'Conexão',
    AppErrorOrigin.peripheral => 'Periférico',
    AppErrorOrigin.localNetwork => 'Rede local',
    AppErrorOrigin.application => 'Aplicativo',
  };

  /// Texto completo copiado pelo operador para abrir um chamado.
  String toClipboardText() => [
    title,
    message,
    if (code != null) 'Código: $code',
    'Origem: $originLabel',
    'Data: ${occurredAt.toIso8601String()}',
    if (recommendedAction != null) 'Ação: $recommendedAction',
    if (technicalDetails != null) 'Detalhes: $technicalDetails',
  ].join('\n');

  static String _titleForStatus(int? status) => switch (status) {
    null => 'Servidor indisponível',
    401 => 'Sessão inválida',
    403 => 'Permissão insuficiente',
    404 => 'Registro não encontrado',
    409 => 'Conflito com o estado atual',
    422 || 400 => 'Dados inconsistentes',
    429 => 'Muitas solicitações',
    _ when status >= 500 => 'Falha no servidor',
    _ => 'Não foi possível concluir',
  };

  static String? _actionForStatus(int? status) => switch (status) {
    null => 'Verifique a rede e tente novamente.',
    401 => 'Entre novamente com seu usuário.',
    403 => 'Solicite a permissão ao responsável pelo restaurante.',
    409 => 'Atualize a tela para ver o estado atual antes de repetir.',
    422 || 400 => 'Corrija os dados destacados e repita a operação.',
    429 => 'Aguarde alguns segundos antes de tentar de novo.',
    _ when status >= 500 => 'Tente novamente; o servidor pode se recuperar.',
    _ => null,
  };
}
