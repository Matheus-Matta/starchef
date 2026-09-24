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

  /// A página das comandas: consulta e conferência, não venda.
  commands,

  /// Lista de clientes: consulta e cadastro.
  customers,

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
    PdvScreen.commands ||
    PdvScreen.scale => true,
    // Clientes não lê código: o leitor do balcão lê comanda e produto, e um
    // código caindo aqui só encheria o campo de busca com o que ele não acha.
    PdvScreen.customers ||
    PdvScreen.payment ||
    PdvScreen.cash ||
    PdvScreen.settings => false,
  };

  /// A balança tem o próprio roteamento (comanda + produto + peso), então o
  /// roteador central não interfere lá.
  bool get hasOwnScannerFlow => this == PdvScreen.scale;

  String get label => switch (this) {
    PdvScreen.home => 'Início',
    PdvScreen.context => 'Comandas e mesas',
    PdvScreen.order => 'Edição do pedido',
    PdvScreen.orders => 'Pedidos',
    PdvScreen.commands => 'Comandas',
    PdvScreen.customers => 'Clientes',
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
      'Procura o produto pelo código de barras e depois pelo código interno. '
          'Não sendo produto, procura a comanda: com o carrinho ainda montando '
          'ela é anexada ao pedido; com o pedido já aberto, abre o pedido dela.',
    PdvScreen.orders =>
      'Procura a comanda e abre o pedido em aberto dela; não encontrando, '
          'preenche a busca da lista.',
    PdvScreen.commands =>
      'Abre a comanda do cartão NESTA tela, sem sair para o pedido dela: aqui '
          'se consulta e se confere, não se vende.',
    PdvScreen.customers => 'Códigos são ignorados.',
    PdvScreen.payment => 'Códigos são ignorados.',
    PdvScreen.cash => 'Códigos são ignorados.',
    PdvScreen.settings => 'Códigos são ignorados.',
    PdvScreen.scale => 'Interpretação própria da balança (comanda e produto).',
  };
}
