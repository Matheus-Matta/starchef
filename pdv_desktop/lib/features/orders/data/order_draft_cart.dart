import 'order_draft.dart';

/// O rascunho inteiro: para onde vai e o que tem dentro.
///
/// Fica separado de [OrderDraftLine] porque são dois assuntos: a linha é um
/// valor imutável, e isto aqui é o que MUDA enquanto o operador monta o
/// pedido.
class OrderDraftCart {
  OrderDraftCart();

  final List<OrderDraftLine> _lines = [];
  int _sequence = 0;

  /// Para onde este rascunho vai: `counter`, `command`, `takeaway`,
  /// `delivery`. É o que a barra no topo do carrinho escolhe.
  String orderType = 'counter';

  /// As comandas ANEXADAS — atributos do rascunho, não gestos que criam
  /// pedido. Anexar e soltar não falam com o servidor.
  ///
  /// É uma LISTA porque a mesa com quatro cartões que paga junto é o caso
  /// comum, não a exceção: o caixa lê os quatro e cobra uma vez. Com mais de
  /// uma, a materialização monta uma conta agrupada em vez de um pedido
  /// simples — as regras de quem pode entrar são do servidor.
  final List<Map<String, dynamic>> commands = [];

  /// O que cada comanda JÁ TEM lançado, vindo do servidor, por id de comanda.
  ///
  /// Anexar um cartão em uso é trazer a conta dele para o pedido que está
  /// sendo cobrado — sem isso, o operador anexava a comanda 3 e via um
  /// carrinho vazio, sem os R$ 45 que o garçom já tinha lançado nela.
  ///
  /// Estes itens **não são do rascunho**: já existem no pedido de cada comanda,
  /// e é por isso que a materialização não os reenvia. Aqui são só leitura —
  /// mexer neles é mexer no pedido de verdade, e isso tem outro caminho.
  final Map<String, List<Map<String, dynamic>>> commandItems = {};

  /// A primeira comanda anexada.
  ///
  /// Ela tem um papel próprio na conta agrupada: é a origem com que a
  /// consolidação é ABERTA, e as outras entram depois. Fora isso, o cabeçalho
  /// do carrinho usa este valor quando há só uma.
  Map<String, dynamic>? get command =>
      commands.isEmpty ? null : commands.first;

  bool get temVariasComandas => commands.length > 1;

  /// Marca que distingue "já lançado na comanda" de "acabei de passar".
  ///
  /// Vai no próprio item porque o carrinho é uma lista só: sem ela, o contador
  /// de quantidade tentaria editar localmente um item que vive no servidor e
  /// não acharia nada — falhando em silêncio, que é o pior resultado.
  static const marcaDeJaLancado = '_ja_lancado';

  /// O número da comanda de onde o item veio, para a conferência em voz alta.
  static const marcaDaComanda = '_da_comanda';

  Map<String, dynamic>? table;
  Map<String, dynamic>? customer;

  List<OrderDraftLine> get lines => List.unmodifiable(_lines);

  /// Não há NADA a cobrar — nem o que a comanda trouxe, nem o que foi passado.
  ///
  /// É diferente de [semLinhasNovas]: uma comanda com R$ 45 lançados e nenhum
  /// item novo tem muito a cobrar, e o botão de pagamento precisa estar aceso.
  /// Confundir os dois deixava o caixa sem como receber a conta da mesa.
  bool get isEmpty => _lines.isEmpty && commands.isEmpty;
  bool get isNotEmpty => !isEmpty;

  /// Nada foi passado nesta tela. O que a comanda já tinha não conta.
  bool get semLinhasNovas => _lines.isEmpty;

  /// Quantas linhas se perdem ao descartar o rascunho.
  ///
  /// Só as novas: o que já estava na comanda continua lá, no pedido dela.
  int get itemCount => _lines.length;

  /// Os itens já lançados, de TODAS as comandas anexadas, na ordem em que os
  /// cartões entraram.
  List<Map<String, dynamic>> get itensJaLancados => [
    for (final comanda in commands)
      ...?commandItems['${comanda['id']}'],
  ];

  /// O que as comandas já tinham, em dinheiro.
  double get commandTotal => itensJaLancados.fold(
    0,
    (soma, item) => soma + (num.tryParse('${item['total_price'] ?? 0}') ?? 0),
  );

  /// Tudo o que vai ser cobrado: o que já estava na comanda mais o que acabou
  /// de ser passado.
  double get total =>
      commandTotal + _lines.fold(0.0, (soma, linha) => soma + linha.total);

  /// A lista inteira do carrinho: primeiro o que já estava lançado, depois o
  /// que está sendo montado agora. Nessa ordem porque é a do atendimento — o
  /// consumo da mesa veio antes do que o caixa está acrescentando.
  List<Map<String, dynamic>> get cartItems => [
    for (final comanda in commands)
      ...?commandItems['${comanda['id']}']?.map(
        (item) => {
          ...item,
          marcaDeJaLancado: true,
          // Com vários cartões na mesma conta, "de quem é este item" vira a
          // pergunta do cliente conferindo em voz alta. Sem isto, a lista
          // seria um amontoado sem dono.
          marcaDaComanda: '${comanda['number'] ?? ''}',
        },
      ),
    ..._lines.map((linha) => linha.toCartItem()),
  ];

  /// Inclui uma linha, somando na existente quando é o mesmo lançamento.
  ///
  /// Agrupar importa na tela: três cafés viram "3 × Café" em vez de três
  /// linhas iguais que o operador tem de contar com o dedo para conferir.
  void add(OrderDraftLine line) {
    final pronta = line.id.isEmpty
        ? OrderDraftLine(
            id: 'rascunho-${++_sequence}',
            productId: line.productId,
            productName: line.productName,
            quantity: line.quantity,
            unitPrice: line.unitPrice,
            variationId: line.variationId,
            addonIds: line.addonIds,
            customerNote: line.customerNote,
            weightKg: line.weightKg,
            scaleReadingId: line.scaleReadingId,
            pricingUnit: line.pricingUnit,
          )
        : line;

    final indice = _lines.indexWhere((atual) => atual.matches(pronta));
    if (indice >= 0) {
      _lines[indice] = _lines[indice].copyWith(
        quantity: _lines[indice].quantity + pronta.quantity,
      );
      return;
    }
    _lines.add(pronta);
  }

  /// Muda a quantidade de uma linha. Zero ou menos REMOVE.
  ///
  /// Remover ao chegar em zero é o que o operador espera do botão de menos, e
  /// evita a linha fantasma "0 × Café" ocupando o carrinho.
  void changeQuantity(String id, double quantity) {
    final indice = _lines.indexWhere((linha) => linha.id == id);
    if (indice < 0) return;
    if (quantity <= 0) {
      _lines.removeAt(indice);
      return;
    }
    _lines[indice] = _lines[indice].copyWith(quantity: quantity);
  }

  void remove(String id) => _lines.removeWhere((linha) => linha.id == id);

  /// Esvazia tudo, inclusive o destino.
  ///
  /// Chamado DEPOIS que a navegação para o pedido aberto deu certo. Limpar
  /// antes custaria o carrinho inteiro se a tela seguinte falhasse ao carregar
  /// — e o operador teria de digitar tudo de novo com o cliente na frente.
  void clear() {
    _lines.clear();
    orderType = 'counter';
    commands.clear();
    commandItems.clear();
    table = null;
    customer = null;
  }

  /// Anexa a comanda. A mesa vem DELA: é a comanda que decide a ocupação do
  /// salão, e o pedido guarda a mesa só como histórico.
}
