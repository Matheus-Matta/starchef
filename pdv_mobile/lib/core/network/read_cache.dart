import 'dart:async';

/// Última resposta das leituras de CATÁLOGO, para a tela abrir na hora.
///
/// O mesmo desenho do PDV desktop (`ResponseCache`): não é fonte de verdade.
/// Até [fresh] a cópia vale como está; até [maxAge] ela aparece na hora e é
/// relida por trás para a próxima abertura; depois disso a leitura espera o
/// servidor. Só entra cardápio e formas de pagamento — nunca pedido,
/// comanda, mesa ou caixa, que mudam a todo instante e decidem dinheiro.
///
/// O app não tem tempo real para invalidar por evento, por isso o prazo curto
/// de [fresh]: um preço trocado no painel aparece na abertura seguinte.
class ReadCache {
  ReadCache({
    this.fresh = const Duration(seconds: 30),
    this.maxAge = const Duration(minutes: 30),
    this.maxEntries = 80,
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  final Duration fresh;
  final Duration maxAge;
  final int maxEntries;
  final DateTime Function() _clock;
  // Literal de mapa guarda a ordem de inserção: a primeira chave é a mais
  // antiga, e é ela que sai quando o limite estoura.
  final _entries = <String, _Entry>{};
  final _inFlight = <String, Future<Map<String, dynamic>>>{};

  Future<Map<String, dynamic>> read(
    String key,
    Future<Map<String, dynamic>> Function() fetch,
  ) async {
    final entry = _entries[key];
    final age = entry == null ? null : _clock().difference(entry.at);
    if (entry != null && age! <= fresh) return entry.value;
    if (entry != null && age! <= maxAge) {
      unawaited(_refresh(key, fetch).catchError((_) => entry.value));
      return entry.value;
    }
    return _refresh(key, fetch);
  }

  /// Uma leitura por chave: duas telas pedindo o cardápio juntas, uma ida.
  Future<Map<String, dynamic>> _refresh(
    String key,
    Future<Map<String, dynamic>> Function() fetch,
  ) {
    final running = _inFlight[key];
    if (running != null) return running;
    final future = fetch()
        .then((value) {
          _entries.remove(key);
          _entries[key] = _Entry(value, _clock());
          while (_entries.length > maxEntries) {
            _entries.remove(_entries.keys.first);
          }
          return value;
        })
        // Bloco, e não `=> _inFlight.remove(key)`: o `remove` devolve o
        // próprio futuro, e o `whenComplete` ficaria esperando por ele mesmo.
        .whenComplete(() {
          _inFlight.remove(key);
        });
    return _inFlight[key] = future;
  }

  void clear() {
    _entries.clear();
    _inFlight.clear();
  }
}

class _Entry {
  _Entry(this.value, this.at);
  final Map<String, dynamic> value;
  final DateTime at;
}
