import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';

/// A NFC-e do pedido, procurada PELO PEDIDO quando a emissão não respondeu.
///
/// A nota nasce sozinha no servidor quando o pedido é pago (em segundo
/// plano). O `/invoices/emit/` do PDV pode falhar mesmo com ela existindo: a
/// SEFAZ lenta passa dos 20 s do terminal, ou o pedido dele esbarra na
/// emissão automática. Antes o PDV desistia ali e o DANFE não saía; agora ele
/// procura a nota no pedido (`fiscal`) por alguns segundos antes de desistir.
class NotaDoPedido {
  const NotaDoPedido(
    this.api, {
    required this.accessToken,
    this.esperas = padrao,
  });

  /// As pausas entre as consultas; cerca de 20 s ao todo.
  static const padrao = [
    Duration(seconds: 1),
    Duration(seconds: 2),
    Duration(seconds: 3),
    Duration(seconds: 4),
    Duration(seconds: 5),
    Duration(seconds: 5),
  ];

  final ApiClient api;
  final String accessToken;
  final List<Duration> esperas;

  /// O bloco `fiscal` do pedido (id, estado, imprimível, número), ou `null`
  /// se a nota não apareceu na janela.
  Future<Map<String, dynamic>?> esperar(String pedidoId) async {
    for (var volta = 0; volta <= esperas.length; volta++) {
      if (volta > 0) await Future<void>.delayed(esperas[volta - 1]);
      try {
        final pedido = await api.get(
          '/orders/$pedidoId/',
          accessToken: accessToken,
        );
        final fiscal = pedido['fiscal'];
        if (fiscal is Map && '${fiscal['id'] ?? ''}'.isNotEmpty) {
          return Map<String, dynamic>.from(fiscal);
        }
      } on ApiException {
        // Um tropeço de rede não encerra a procura: a próxima volta tenta.
      }
    }
    return null;
  }
}
