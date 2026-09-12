/// Dados variados, toscos e invalidos — o operador apressado de verdade.
///
/// A regra que o teste cobra do nucleo local e a mesma cobrada do backend:
/// **entrada errada vira recusa clara; nunca excecao solta, nunca gravacao
/// silenciosa de lixo**.
library;

import 'dart:math';

class Baralho {
  Baralho(int semente) : _acaso = Random(semente);

  final Random _acaso;

  static const nomes = [
    'Ana', 'Bruno', 'Carla', 'Diego', 'Eduarda', 'Fabio', 'Gabriela',
    'Henrique', 'Isabela', 'Joao', 'Karina', 'Lucas', 'Mariana', 'Pedro',
  ];
  static const pratos = [
    'X-Burger', 'Picanha na Chapa', 'Feijoada', 'Acai 500ml', 'Coxinha',
    'Suco de Laranja', 'Guarana Lata', 'Buffet por Kg', 'Pudim', 'Caipirinha',
  ];
  static const sujeira = [
    '', '   ', 'N/A', '-', '?', 'NAO SEI', '123', 'null', 'undefined',
    "'; DROP TABLE orders;--", '<script>alert(1)</script>', 'ÇÃOÊÉÍÓÚ',
  ];

  double sorteio() => _acaso.nextDouble();
  bool chance(double probabilidade) => _acaso.nextDouble() < probabilidade;
  int inteiro(int limite) => _acaso.nextInt(limite);

  T escolher<T>(List<T> opcoes) => opcoes[_acaso.nextInt(opcoes.length)];

  String pessoa() => '${escolher(nomes)} ${escolher(nomes)}';

  String observacao() =>
      chance(0.2) ? escolher(sujeira) : escolher(['sem cebola', 'bem passado', 'pra viagem']);

  double peso() => chance(0.05)
      ? 150 + _acaso.nextDouble() * 200
      : 0.08 + _acaso.nextDouble() * 2.3;
}

/// Uma variacao invalida de payload, com o nome do caso que ela representa.
class CasoInvalido {
  const CasoInvalido(this.nome, this.corpo);

  final String nome;
  final Map<String, dynamic> corpo;
}

/// Item de pedido preenchido errado, do jeito que acontece no balcao.
///
/// `quantity: null` NAO entra na lista: o backend trata ausente e nulo da mesma
/// forma (assume 1, que e o comportamento de bipar um produto), e cobrar do PDV
/// uma regra que o servidor nao tem so criaria divergencia entre os dois.
List<CasoInvalido> itensInvalidos(String produtoValido) => [
  const CasoInvalido('item_sem_produto', {'quantity': 1}),
  CasoInvalido('quantidade_zero', {'product': produtoValido, 'quantity': 0}),
  CasoInvalido('quantidade_negativa', {'product': produtoValido, 'quantity': -3}),
  CasoInvalido('quantidade_texto', {'product': produtoValido, 'quantity': 'duas'}),
  const CasoInvalido('produto_inexistente', {
    'product': 'produto-que-nao-existe',
    'quantity': 1,
  }),
  CasoInvalido('quantidade_absurda', {
    'product': produtoValido,
    'quantity': 1000000000000,
  }),
];

/// Fechamento com desconto que nao deveria passar.
const fechamentosInvalidos = [
  CasoInvalido('desconto_negativo', {'discount': -50, 'service_fee_enabled': false}),
  CasoInvalido('desconto_texto', {'discount': 'dez reais'}),
  CasoInvalido('desconto_maior_que_total', {'discount': 999999}),
];

/// Recebimento incompleto ou incoerente.
const recebimentosInvalidos = [
  CasoInvalido('pagamento_sem_valor', {'payment_method': 'dinheiro'}),
  CasoInvalido('pagamento_sem_forma', {'amount': '10.00'}),
  CasoInvalido('valor_texto', {'payment_method': 'dinheiro', 'amount': 'vinte reais'}),
  CasoInvalido('valor_negativo', {'payment_method': 'dinheiro', 'amount': '-99.90'}),
  CasoInvalido('forma_inexistente', {
    'payment_method': 'forma-que-nao-existe',
    'amount': '10.00',
  }),
];

/// Movimentacao de caixa mal preenchida.
const caixaInvalido = [
  CasoInvalido('abertura_sem_estacao', {'opening_amount': '100.00'}),
  CasoInvalido('abertura_valor_texto', {
    'cash_station': 'caixa-1',
    'opening_amount': 'cem reais',
  }),
  CasoInvalido('sangria_sem_valor', {'reason': 'troco'}),
  CasoInvalido('sangria_negativa', {'amount': '-500', 'reason': 'troco'}),
  CasoInvalido('fechamento_sem_valor', {'notes': 'conferido'}),
];

/// Consultas que a tela faz e que precisam responder sem quebrar.
const leiturasHostis = [
  {'page': 1, 'page_size': 20},
  {'page': 99999, 'page_size': 50},
  {'page': 'abc', 'page_size': -5},
  {'search': "' OR 1=1--"},
  {'search': '<script>'},
  {'page_size': 100000},
  {'ordering': 'campo_que_nao_existe'},
  {'campo_inventado': 'x', 'is_active': 'talvez'},
];
