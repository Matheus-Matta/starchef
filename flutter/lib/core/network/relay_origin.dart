import 'dart:async';

/// Quem originou uma operação que o Caixa Principal está executando por outro.
///
/// O Caixa Secundário **nunca fala com o servidor**: tudo passa pelo Principal.
/// Mas o Principal executar com as credenciais dele faria toda venda de um
/// secundário nascer no nome do principal — o pedido com o atendente errado, e
/// a sessão de caixa com o dono errado, que é justamente a regra que a
/// exclusividade precisa cumprir.
///
/// Então o secundário gera as próprias credenciais (o login dele, com o próprio
/// operador e a própria instalação), envia junto da operação, e o Principal
/// **encaminha** com elas. O SQLite do principal guarda a operação com essas
/// credenciais: a fila dele entrega no nome de quem originou, não no dele.
///
/// O `refreshToken` viaja porque a fila é durável: uma operação pode esperar
/// horas até a nuvem voltar, e o access token do secundário já teria vencido.
/// Sem ele, uma queda longa transformaria a fila inteira em pendência manual.
class RelayOrigin {
  const RelayOrigin({
    required this.accessToken,
    required this.actorId,
    this.refreshToken = '',
    this.actorName = '',
    this.installationId = '',
    this.terminalName = '',
  });

  final String accessToken;
  final String refreshToken;

  /// Id do operador que está na frente do terminal de origem.
  final String actorId;
  final String actorName;

  /// UUID da instalação de origem — vira o `X-Terminal-Id` do encaminhamento.
  final String installationId;
  final String terminalName;

  bool get isUsable => accessToken.trim().isNotEmpty && actorId.trim().isNotEmpty;

  /// Substitui os tokens depois de uma renovação.
  ///
  /// O refresh também entra: o backend rotaciona e coloca o anterior na lista
  /// negra, então guardar só o access faria a SEGUNDA renovação falhar — e a
  /// operação do secundário viraria pendência manual justamente depois de uma
  /// queda longa, que é quando isto mais importa.
  RelayOrigin withTokens({required String access, String? refresh}) =>
      RelayOrigin(
        accessToken: access,
        refreshToken: (refresh ?? '').isNotEmpty ? refresh! : refreshToken,
        actorId: actorId,
        actorName: actorName,
        installationId: installationId,
        terminalName: terminalName,
      );

  Map<String, dynamic> toJson() => {
    'access': accessToken,
    'refresh': refreshToken,
    'actor_id': actorId,
    'actor_name': actorName,
    'installation_id': installationId,
    'terminal_name': terminalName,
  };

  static RelayOrigin? fromJson(Object? json) {
    if (json is! Map) return null;
    final origin = RelayOrigin(
      accessToken: '${json['access'] ?? ''}',
      refreshToken: '${json['refresh'] ?? ''}',
      actorId: '${json['actor_id'] ?? ''}',
      actorName: '${json['actor_name'] ?? ''}',
      installationId: '${json['installation_id'] ?? ''}',
      terminalName: '${json['terminal_name'] ?? ''}',
    );
    return origin.isUsable ? origin : null;
  }

  // ------------------------------------------------------------------ escopo

  static const _zoneKey = #starchefRelayOrigin;

  /// A origem da operação que está sendo executada AGORA, se houver.
  ///
  /// Vive em uma [Zone] em vez de um campo do gateway de propósito: o principal
  /// executa a operação de um secundário e as suas próprias no mesmo isolate, e
  /// um campo compartilhado seria lido pela operação errada no primeiro `await`
  /// que as intercalasse — o principal carimbaria a própria venda com as
  /// credenciais do secundário. A zona acompanha a cadeia de chamadas, não o
  /// relógio.
  static RelayOrigin? get current {
    final value = Zone.current[_zoneKey];
    return value is RelayOrigin ? value : null;
  }

  /// Executa [body] atribuindo tudo o que ele gravar a esta origem.
  static Future<T> runAs<T>(RelayOrigin? origin, Future<T> Function() body) {
    if (origin == null) return body();
    return runZoned(body, zoneValues: {_zoneKey: origin});
  }
}
