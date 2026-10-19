import '../../../core/logging/app_logger.dart';

/// O rastro da venda no `pdv.log`: quando saiu, quanto levou, como voltou.
///
/// Uma venda que "não finalizou por algum motivo" não deixava nada no log —
/// só o título do alerta, sem o pedido. Com o id e o número dela, a pergunta
/// "o que houve com o pedido #1234?" passa a ter resposta.
void rastroDaVenda(
  String evento, {
  required String pedido,
  Map<String, Object?> dados = const {},
  bool falhou = false,
}) {
  final registro = {'pedido': pedido, ...dados};
  if (falhou) {
    AppLogger.instance.warning(evento, data: registro);
  } else {
    AppLogger.instance.info(evento, data: registro);
  }
}

/// Envia `chamada` registrando o começo, o fim (com o número do pedido) e a
/// falha — sempre com o tempo que levou.
Future<Map<String, dynamic>> comRastro(
  String operacao, {
  required String pedido,
  required Map<String, Object?> dados,
  required Future<Map<String, dynamic>> Function() chamada,
}) async {
  final relogio = Stopwatch()..start();
  rastroDaVenda('${operacao}_enviada', pedido: pedido, dados: dados);
  try {
    final resposta = await chamada();
    final pedidoGravado = resposta['order'];
    rastroDaVenda(
      '${operacao}_ok',
      pedido: pedido,
      dados: {
        'sequencia': pedidoGravado is Map ? pedidoGravado['sequence'] : null,
        'ms': relogio.elapsedMilliseconds,
      },
    );
    return resposta;
  } catch (erro) {
    rastroDaVenda(
      '${operacao}_falhou',
      pedido: pedido,
      dados: {'erro': '$erro', 'ms': relogio.elapsedMilliseconds},
      falhou: true,
    );
    rethrow;
  }
}
