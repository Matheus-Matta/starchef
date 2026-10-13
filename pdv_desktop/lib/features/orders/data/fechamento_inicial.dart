/// O fechamento que vai JÁ na primeira simulação da venda.
///
/// Ir ao pagamento simulava DUAS vezes: a primeira só para ler a taxa, o CPF e
/// o cupom padrão do pedido, a segunda reenviando esses mesmos valores no
/// fechamento. Na nuvem eram duas idas inteiras ao servidor — uns 3 s com o
/// cliente esperando. Taxa, CPF/CNPJ e cupom AUSENTES querem dizer "o padrão
/// do pedido" no `close_order`, então uma simulação já devolve o total certo.
///
/// Só o desconto vai: o rascunho não tem desconto, e o fechamento precisa de
/// um campo para existir.
Map<String, dynamic> fechamentoInicial() => {'discount': 0};
