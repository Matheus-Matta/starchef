/// Onde o operador está — a única coisa que decide como um código é lido.
///
/// Um mesmo "7891000100103" significa coisas diferentes conforme a tela: no
/// início é uma comanda a abrir; na edição do pedido é um produto a lançar; no
/// pagamento não é nada. Sem esse enum, cada tela precisaria adivinhar se o
/// texto que chegou era para ela — e o resultado prático seria um EAN abrindo
/// uma ação inesperada em uma tela que não deveria reagir a códigos.
enum PdvScreen {
  /// Início / nova venda.
  home,

  /// Escolha de comanda ou mesa.
  context,

  /// Edição do pedido (lançamento de itens).
  order,

  /// Lista de pedidos.
  orders,

  /// Fechamento e recebimento.
  payment,

  /// Caixa e financeiro.
  cash,

  /// Configurações.
  settings,

  /// Balança rápida — tem interpretação própria de comanda/produto.
  scale;

  /// A tela reage a um código lido?
  ///
  /// Pagamento, caixa e configurações não reagem de propósito: são telas onde
  /// um código lido por engano (ou o Enter que o leitor envia no fim) faria
  /// estrago — confirmar um recebimento, fechar um caixa.
  bool get readsCodes => switch (this) {
    PdvScreen.home ||
    PdvScreen.context ||
    PdvScreen.order ||
    PdvScreen.orders ||
    PdvScreen.scale => true,
    PdvScreen.payment || PdvScreen.cash || PdvScreen.settings => false,
  };

  /// A balança tem o próprio roteamento (comanda + produto + peso), então o
  /// roteador central não interfere lá.
  bool get hasOwnScannerFlow => this == PdvScreen.scale;

  String get label => switch (this) {
    PdvScreen.home => 'Início',
    PdvScreen.context => 'Comandas e mesas',
    PdvScreen.order => 'Edição do pedido',
    PdvScreen.orders => 'Pedidos',
    PdvScreen.payment => 'Pagamento',
    PdvScreen.cash => 'Caixa',
    PdvScreen.settings => 'Configurações',
    PdvScreen.scale => 'Balança rápida',
  };

  /// O que a tela faz com um código, em uma frase — usada na página de ajuda.
  String get codeBehaviour => switch (this) {
    PdvScreen.home =>
      'Procura a comanda e abre o pedido em aberto dela. Não encontrando, '
          'nada acontece — sem aviso, para o operador poder continuar lendo.',
    PdvScreen.context =>
      'Procura a comanda e abre o pedido em aberto dela.',
    PdvScreen.order =>
      'Procura o produto pelo código de barras e depois pelo código interno, '
          'e abre a configuração do item.',
    PdvScreen.orders => 'Preenche a busca da lista. Não abre nada sozinho.',
    PdvScreen.payment => 'Códigos são ignorados.',
    PdvScreen.cash => 'Códigos são ignorados.',
    PdvScreen.settings => 'Códigos são ignorados.',
    PdvScreen.scale => 'Interpretação própria da balança (comanda e produto).',
  };
}
