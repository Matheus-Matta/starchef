import 'dart:async';
import 'dart:convert';

import '../../../core/network/api_client.dart';

/// As listas que a Balança Rápida lê ao abrir, primeiro do CACHE.
///
/// Restaurantes, cardápio, balanças e impressoras mudam pouco e eram lidos em
/// SEQUÊNCIA, um esperando o outro, a cada abertura da estação. Agora: havendo
/// a última resposta guardada (`response_cache.dart`, que sobrevive a
/// reiniciar o PDV), ela volta NA HORA e a leitura do servidor corre em
/// segundo plano. Se o servidor trouxer algo diferente, [aoAtualizar] recebe a
/// lista nova. Sem nada guardado — a primeira abertura —, espera a rede, como
/// antes.
///
/// Nada aqui decide dinheiro: o preço da pesagem é o do servidor, no
/// lançamento. Uma lista velha por alguns segundos só atrasa um nome na tela.
class ListaDaEstacao {
  const ListaDaEstacao(this.api, {required this.accessToken});

  final ApiClient api;
  final String accessToken;

  Future<List<Map<String, dynamic>>> ler(
    String path, {
    required Map<String, dynamic> query,
    void Function(List<Map<String, dynamic>> nova)? aoAtualizar,
  }) async {
    final guardada = api.peek(path, query: query, accessToken: accessToken);
    if (guardada == null) return _doServidor(path, query);
    final mostrada = _resultados(guardada);
    unawaited(
      _doServidor(path, query).then(
        (nova) {
          if (jsonEncode(nova) != jsonEncode(mostrada)) aoAtualizar?.call(nova);
        },
        onError: (_) {
          // Sem rede: a estação segue com o que tinha; a próxima abertura relê.
        },
      ),
    );
    return mostrada;
  }

  Future<List<Map<String, dynamic>>> _doServidor(
    String path,
    Map<String, dynamic> query,
  ) async =>
      _resultados(await api.get(path, query: query, accessToken: accessToken));

  /// `toList()` converte AGORA: resposta torta estoura aqui, no `try` de quem
  /// chamou, e não depois, ao desenhar — onde a tela ficava em "carregando".
  static List<Map<String, dynamic>> _resultados(
    Map<String, dynamic> resposta,
  ) => ((resposta['results'] ?? const []) as List)
      .cast<Map<String, dynamic>>()
      .toList();
}
