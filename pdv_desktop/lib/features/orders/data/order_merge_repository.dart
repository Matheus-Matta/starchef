import '../../../core/formatters/value_formatters.dart';
import '../../../core/network/api_client.dart';

/// A conta agrupada de comandas, do lado do PDV desktop.
///
/// Uma mesa com quatro comandas de uma família: o pai paga tudo. O caixa lê as
/// quatro (ou inclui à mão), os itens das quatro entram num pedido só, e ele
/// cobra uma vez.
///
/// Toda chamada devolve o RESUMO inteiro — comandas, itens e total —, e não
/// apenas o registro alterado. É de propósito: a lista que o caixa está lendo
/// em voz alta para o cliente não pode ser montada de pedaços vindos de
/// respostas diferentes, porque é assim que ela passa a divergir do servidor.
class OrderMergeRepository {
  const OrderMergeRepository(this._api, {this.accessToken});

  final ApiClient _api;

  /// A credencial do operador.
  ///
  /// Sem ela toda chamada daqui volta 401 — e era o que acontecia: o
  /// repositório nascia só com o cliente HTTP, e o `ApiClient` não guarda
  /// token nenhum. A conta agrupada inteira do desktop não passava do primeiro
  /// clique.
  final String? accessToken;

  /// Abre a conta com o pedido DESTA comanda como primeira origem.
  ///
  /// O destino é sempre um pedido novo: a primeira comanda também precisa
  /// preservar o pedido e os lotes dela, e tratá-la como origem e destino ao
  /// mesmo tempo duplicaria ou perderia itens e taxa.
  Future<Map<String, dynamic>> open(String orderId) =>
      _api.post('/orders/$orderId/merge/', body: const {}, accessToken: accessToken);

  Future<Map<String, dynamic>> load(String mergeId) =>
      _api.get('/orders/merges/$mergeId/', accessToken: accessToken);

  /// Inclui por código de barras, número impresso ou id.
  ///
  /// Bipar a mesma comanda de novo é idempotente no servidor: o leitor dispara
  /// duas leituras com frequência, e transformar isso em erro ensinaria o
  /// operador a ignorar mensagens.
  Future<Map<String, dynamic>> addCommand(String mergeId, String reference) =>
      _api.post(
        '/orders/merges/$mergeId/commands/',
        body: {'command': reference},
        accessToken: accessToken,
      );

  Future<Map<String, dynamic>> removeCommand(
    String mergeId,
    String commandId,
  ) => _api.delete(
        '/orders/merges/$mergeId/commands/$commandId/',
        accessToken: accessToken,
      );

  /// Confirma: os itens das comandas passam para um pedido só.
  ///
  /// `ApiClient` já manda uma chave de idempotência por escrita, então um
  /// clique duplo não monta duas consolidações da mesma mesa.
  Future<Map<String, dynamic>> confirm(String mergeId) =>
      _api.post('/orders/merges/$mergeId/confirm/', body: const {}, accessToken: accessToken);

  Future<Map<String, dynamic>> cancel(String mergeId, {String reason = ''}) =>
      _api.post(
        '/orders/merges/$mergeId/cancel/',
        body: {'reason': reason},
        accessToken: accessToken,
      );

  /// Estorna a conta agrupada JÁ PAGA.
  ///
  /// Não é o mesmo que [cancel]. Desfazer devolve os itens às comandas de uma
  /// conta que ainda não recebeu dinheiro; estornar desmonta uma venda que já
  /// passou por caixa, estoque e nota — e esvazia os cartões, **inclusive
  /// cancelando o pedido de um cartão que já foi reentregue a outro cliente**.
  Future<Map<String, dynamic>> refund(String mergeId, {required String reason}) =>
      _api.post(
        '/orders/merges/$mergeId/refund/',
        body: {'reason': reason},
        accessToken: accessToken,
      );

  /// Imprime a conferência de UMA comanda — e funciona depois do merge.
  ///
  /// O recibo comum sai do pedido, e depois da consolidação o pedido de origem
  /// está vazio: sairia papel em branco. Este lê `OrderItem.command`.
  Future<Map<String, dynamic>> commandReceipt(String commandId) =>
      _api.post('/commands/$commandId/receipt/', body: const {}, accessToken: accessToken);

  /// Resolve o cartão lido para a comanda dele.
  Future<Map<String, dynamic>> commandByCode(String code) =>
      _api.get(
        '/commands/by-code/',
        query: {'code': code},
        accessToken: accessToken,
      );
}

/// Os itens da conta, agrupados POR COMANDA — é como o cliente pergunta.
///
/// Uma lista corrida de produtos responde "quanto deu"; ela não responde "de
/// quem é isto", que é a pergunta que aparece com quatro comandas numa conta.
List<MergeCommandGroup> groupMergeItems(Map<String, dynamic> merge) {
  final grupos = <String, MergeCommandGroup>{};
  for (final bruto in (merge['items'] as List? ?? const [])) {
    if (bruto is! Map) continue;
    final item = Map<String, dynamic>.from(bruto);
    final chave = '${item['command'] ?? 'sem-comanda'}';
    final grupo = grupos.putIfAbsent(
      chave,
      () => MergeCommandGroup(
        commandId: '${item['command'] ?? ''}',
        number: item['command_number'],
        code: '${item['command_code'] ?? ''}',
      ),
    );
    grupo.items.add(item);
    grupo.total += ValueFormatters.number(item['total_price']);
  }
  final lista = grupos.values.toList();
  lista.sort((a, b) => _asInt(a.number).compareTo(_asInt(b.number)));
  return lista;
}

int _asInt(Object? value) => ValueFormatters.integer(value);

class MergeCommandGroup {
  MergeCommandGroup({
    required this.commandId,
    required this.number,
    required this.code,
  });

  final String commandId;
  final Object? number;
  final String code;
  final List<Map<String, dynamic>> items = [];
  double total = 0;
}
