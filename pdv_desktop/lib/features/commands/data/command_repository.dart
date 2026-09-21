import '../../../core/network/api_client.dart';
import '../../../core/network/api_exception.dart';

/// O que uma comanda tem — e o que ela já teve.
///
/// Estas rotas existem porque `command.items` no backend devolve o HISTÓRICO
/// INTEIRO do cartão, inclusive almoços de semanas atrás. "O que tem nesta
/// comanda agora" e "o que este cartão já consumiu" são perguntas diferentes,
/// e misturá-las faz a comanda reutilizada reaparecer cheia com a conta do
/// cliente anterior.
///
/// Elas também são o que mantém a comanda legível **depois** da conta
/// agrupada: ali os itens passam a viver no pedido consolidado, e só
/// `OrderItem.command` responde de quem cada um é.
class CommandRepository {
  const CommandRepository(this._api, {this.accessToken});

  final ApiClient _api;
  final String? accessToken;

  /// As comandas ativas do restaurante.
  ///
  /// Cada uma traz `closing_merge`: o id da conta agrupada que a está
  /// segurando, ou vazio. "Em fechamento" é derivado disso, nunca de um estado
  /// gravado na comanda — um terceiro estado no banco seria mais uma coisa a
  /// sincronizar e a divergir.
  Future<List<Map<String, dynamic>>> list({String? restaurantId}) async {
    final resposta = await _api.get(
      '/commands/',
      query: {
        'page_size': 200,
        'is_active': true,
        if (restaurantId != null && restaurantId.isNotEmpty)
          'restaurant': restaurantId,
      },
      accessToken: accessToken,
    );
    // `results` é a resposta paginada; `data` e a lista crua cobrem uma rota
    // sem paginação. Nenhum dos três sendo lista, a resposta não é o que esta
    // tela sabe ler — e devolver vazio em silêncio faria a página parecer que
    // não tem comanda nenhuma, quando o que houve foi um formato inesperado.
    final bruto = resposta['results'] ?? resposta['data'] ?? const [];
    if (bruto is! List) {
      throw ApiException(
        'O servidor respondeu num formato que esta tela não reconhece.',
      );
    }
    return bruto
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  /// Itens da comanda.
  ///
  /// `history: false` devolve o que está ABERTO no pedido de trabalho atual ou
  /// na consolidação viva; `history: true` devolve tudo o que o cartão já
  /// teve, sem filtro de estado — é o modo relatório.
  Future<Map<String, dynamic>> items(
    String commandId, {
    bool history = false,
  }) => _api.get(
    '/commands/$commandId/items/',
    query: history ? const {'history': 1} : null,
    accessToken: accessToken,
  );

  /// Anota um consumo NA COMANDA. Nenhum pedido é aberto.
  ///
  /// É o gesto central do modelo novo: o cartão é um bloco de notas, e o
  /// pedido só nasce no caixa, com as anotações pendentes.
  Future<Map<String, dynamic>> launchItem(
    String commandId, {
    required String productId,
    num quantity = 1,
    String customerNote = '',
    List<Map<String, dynamic>> variations = const [],
  }) => _api.post(
    '/commands/$commandId/items/',
    body: {
      'product': productId,
      'quantity': quantity,
      'customer_note': customerNote,
      'variations': variations,
    },
    accessToken: accessToken,
  );

  /// Manda a rodada pendente desta comanda para a produção.
  ///
  /// Mesmo gesto do pedido — e é por isso que, ao ser cobrado, o item do
  /// pedido HERDA este envio: sem isso o prato voltaria para o forno quando a
  /// conta fechasse, horas depois.
  Future<Map<String, dynamic>> sendToKitchen(String commandId) => _api.post(
    '/commands/$commandId/send-to-kitchen/',
    body: const {},
    accessToken: accessToken,
  );

  /// Cancela uma anotação. Ela sai da comanda como PERDA, não como venda.
  Future<Map<String, dynamic>> voidItem(
    String commandId,
    String itemId, {
    required String reason,
  }) => _api.delete(
    '/commands/$commandId/items/$itemId/void/',
    body: {'reason': reason},
    accessToken: accessToken,
  );

  /// Imprime a conferência da comanda — antes ou depois do merge.
  ///
  /// **Não é documento fiscal.** A NFC-e é uma só, do pedido consolidado; este
  /// papel é o que o cliente pede quando quer saber "e a comanda 13, quanto
  /// deu?" dentro de uma conta de quatro pessoas.
  Future<Map<String, dynamic>> receipt(String commandId) => _api.post(
    '/commands/$commandId/receipt/',
    body: const {},
    accessToken: accessToken,
  );

  /// Resolve um cartão lido pelo leitor de código de barras.
  Future<Map<String, dynamic>> byCode(String code) =>
      _api.get('/commands/by-code/', query: {'code': code}, accessToken: accessToken);
}

/// A comanda tem VALOR a cobrar.
///
/// É o que decide se o cartão pode ser anexado a um pedido, e o critério é o
/// dinheiro — não a contagem. Um cartão cujas anotações pendentes somam zero
/// (tudo cortesia, por exemplo) não tem nada a receber: anexá-lo produziria um
/// pedido preso a um cartão que não acrescenta um centavo à conta.
///
/// "Em uso" deixou de ser um pedido aberto: a comanda é um bloco de notas, e a
/// listagem manda `pending_total` justamente para a grade não precisar abrir
/// cada cartão para saber.
bool comandaTemContaAberta(Map<String, dynamic> comanda) {
  final total = num.tryParse('${comanda['pending_total'] ?? ''}');
  if (total != null) return total > 0;
  // Servidor antigo, que ainda não manda o valor: a contagem é a melhor
  // resposta disponível, e o retrato de estado é o último recurso. Travar a
  // tela seria pior que responder com o que dá.
  final pendentes = comanda['pending_items'];
  if (pendentes is num) return pendentes > 0;
  return '${comanda['status'] ?? ''}' == 'occupied';
}
