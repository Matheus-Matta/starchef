/// Fase CATALOGO — leitura em massa do SQLite local, do jeito que a tela pede.
///
/// E a fase que responde "a tela abre rapido?". Toda leitura aqui e a mesma
/// que o catalogo de produtos, a lista de pedidos e o seletor de comanda fazem
/// ao serem abertos, inclusive com filtro hostil e pagina que nao existe.
library;

import '../chaos.dart';
import '../metrics.dart';
import '../scenario.dart';
import '../stack.dart';

Future<void> rodar(
  PilhaDeCarga pilha,
  CenarioLocal cenario,
  Medidor medidor,
  Baralho baralho, {
  required int leituras,
}) async {
  final gateway = pilha.gateway;

  for (var indice = 0; indice < leituras; indice++) {
    final sorteio = baralho.sorteio();
    if (sorteio < 0.45) {
      final consulta = Map<String, dynamic>.from(
        baralho.escolher(leiturasHostis),
      )..putIfAbsent('restaurant', () => PilhaDeCarga.restauranteId);
      await medidor.medir(
        'leitura.catalogo',
        () => gateway.read('/menu/products/', query: consulta),
        caso: consulta.containsKey('search') ? 'busca' : 'listagem',
      );
    } else if (sorteio < 0.65) {
      await medidor.medir(
        'leitura.catalogo',
        () => gateway.read('/commands/', query: {
          'page': 1,
          'page_size': 50,
          'restaurant': PilhaDeCarga.restauranteId,
        }),
        caso: 'comandas',
      );
    } else if (sorteio < 0.8) {
      await medidor.medir(
        'leitura.lista_pedidos',
        () => gateway.read('/orders/', query: {
          'page': 1,
          'page_size': 25,
          'restaurant': PilhaDeCarga.restauranteId,
        }),
        caso: 'pedidos',
      );
    } else if (sorteio < 0.9) {
      await medidor.medir(
        'leitura.catalogo',
        () => gateway.read('/tables/', query: {
          'page_size': 100,
          'restaurant': PilhaDeCarga.restauranteId,
        }),
        caso: 'mesas',
      );
    } else {
      // Registro que nao existe: a resposta certa e `_empty`, nunca excecao.
      final resposta = await medidor.medir(
        'leitura.pedido',
        () => gateway.read('/menu/products/prod-que-nao-existe/'),
        caso: 'inexistente',
      );
      if (resposta != null && resposta['_empty'] != true) {
        medidor.registrar(
          Amostra(
            'leitura.pedido',
            0,
            vLixoAceito,
            caso: 'inexistente',
            detalhe: 'leitura de registro inexistente devolveu conteudo: $resposta',
          ),
        );
      }
    }
  }

  // A leitura de colecao tem de continuar paginando certo com a tabela cheia.
  final pagina = await gateway.read('/menu/products/', query: {
    'page': 1,
    'page_size': 20,
    'restaurant': PilhaDeCarga.restauranteId,
  });
  final resultados = (pagina['results'] as List?) ?? const [];
  medidor
    ..verificar(
      'paginacao devolve exatamente o page_size pedido',
      resultados.length == 20,
      detalhe: '${resultados.length} registros na primeira pagina',
    )
    ..verificar(
      'contagem total do catalogo bate com o que foi semeado',
      pagina['count'] == cenario.produtosUnidade.length + 1,
      detalhe: 'count=${pagina['count']}, semeados=${cenario.produtosUnidade.length + 1}',
    )
    ..observar(
      'catalogo semeado com ${cenario.produtosUnidade.length + 1} produtos e '
      '${cenario.comandas.length} comandas',
    );
}
