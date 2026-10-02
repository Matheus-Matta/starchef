import 'dart:collection';
import 'dart:convert';

/// Última resposta das LISTAS do catálogo, para a tela abrir na hora.
///
/// Não é fonte de verdade — o servidor continua sendo. Serve para a primeira
/// renderização: o PDV mostra o que tinha da última vez e, em seguida, a
/// leitura nova substitui. Por isso:
///
/// * só listas de cadastro entram (comandas, produtos, categorias, clientes,
///   mesas, formas de pagamento, estações); pedido, caixa e autenticação,
///   nunca — nada aqui decide pagamento nem fechamento;
/// * a chave leva servidor, conta, usuário, rota e parâmetros (o restaurante
///   vai na consulta): outra conta no mesmo computador nunca vê a lista desta;
/// * qualquer escrita ou evento de tempo real do assunto apaga as entradas
///   dele, e logout/troca de servidor apagam tudo;
/// * memória limitada ([maxEntries], a mais antiga sai) e validade
///   ([maxAge]): passado disso a entrada não é servida.
class ResponseCache {
  ResponseCache({
    this.maxEntries = 120,
    this.maxAge = const Duration(minutes: 30),
    DateTime Function()? clock,
  }) : _clock = clock ?? DateTime.now;

  final int maxEntries;
  final Duration maxAge;
  final DateTime Function() _clock;
  // Literal de mapa do Dart guarda a ordem de inserção: a primeira chave é a
  // mais antiga, e é ela que sai quando o limite estoura.
  final _entries = <String, _Entry>{};

  /// Rotas que entram, e o assunto de cada uma.
  static const _assuntos = {
    '/commands/': 'commands',
    '/menu/products/': 'menu',
    '/menu/categories/': 'menu',
    '/customers/': 'customers',
    '/tables/': 'tables',
    '/payments/methods/': 'payments',
    '/cash-stations/': 'cash',
  };

  /// O que uma escrita em cada rota pode ter mudado. Pedido mexe em comanda
  /// (anexar, cobrar, liberar) e em mesa; caixa mexe na estação.
  static const _escritaAfeta = {
    'commands': {'commands', 'tables'},
    'orders': {'commands', 'tables'},
    'menu': {'menu'},
    'customers': {'customers'},
    'tables': {'tables', 'commands'},
    'payments': {'payments'},
    'cash-stations': {'cash'},
    'cash-register': {'cash'},
  };

  static String? assuntoDe(String path) => _assuntos[path];

  int get length => _entries.length;

  String chave(String escopo, String path, Map<String, dynamic>? query) {
    final ordenada = SplayTreeMap<String, String>.from(
      (query ?? const {}).map((k, v) => MapEntry(k, '$v')),
    );
    return '$escopo|$path?${jsonEncode(ordenada)}';
  }

  /// Guarda a resposta, se a rota for de catálogo.
  void store(
    String escopo,
    String path,
    Map<String, dynamic>? query,
    Map<String, dynamic> resposta,
  ) {
    final assunto = assuntoDe(path);
    if (assunto == null) return;
    final k = chave(escopo, path, query);
    _entries.remove(k);
    _entries[k] = _Entry(assunto, resposta, _clock());
    while (_entries.length > maxEntries) {
      _entries.remove(_entries.keys.first);
    }
  }

  /// A última resposta guardada, ou `null` se não há ou venceu.
  Map<String, dynamic>? peek(
    String escopo,
    String path,
    Map<String, dynamic>? query,
  ) {
    final k = chave(escopo, path, query);
    final entrada = _entries[k];
    if (entrada == null) return null;
    if (_clock().difference(entrada.guardadaEm) > maxAge) {
      _entries.remove(k);
      return null;
    }
    return entrada.resposta;
  }

  /// Há quanto tempo a resposta foi guardada, ou `null` se não há.
  Duration? ageOf(String escopo, String path, Map<String, dynamic>? query) {
    final entrada = _entries[chave(escopo, path, query)];
    return entrada == null ? null : _clock().difference(entrada.guardadaEm);
  }

  /// Uma escrita deste terminal: apaga o que ela pode ter mudado.
  void invalidateForWrite(String path) {
    final segmentos = path.split('/').where((s) => s.isNotEmpty).toList();
    if (segmentos.isEmpty) return;
    invalidate(_escritaAfeta[segmentos.first] ?? const {});
  }

  /// Um evento do servidor (`restaurants.command`, `menu.product`…).
  void invalidateForResource(String resource) {
    final app = resource.split('.').first;
    final modelo = resource.contains('.') ? resource.split('.').last : '';
    final assuntos = <String>{
      if (app == 'orders') ...{'commands', 'tables'},
      if (app == 'menu') 'menu',
      if (app == 'customers') 'customers',
      if (app == 'payments') ...{'payments', 'cash'},
      if (app == 'restaurants') ...{'commands', 'tables'},
      if (app == 'restaurants' && modelo == 'restaurant') ...{
        'menu',
        'payments',
        'cash',
      },
    };
    // Recurso desconhecido: melhor reler tudo do que mostrar dado velho.
    invalidate(assuntos.isEmpty ? _assuntos.values.toSet() : assuntos);
  }

  void invalidate(Set<String> assuntos) {
    _entries.removeWhere((_, entrada) => assuntos.contains(entrada.assunto));
  }

  void clear() => _entries.clear();
}

class _Entry {
  _Entry(this.assunto, this.resposta, this.guardadaEm);

  final String assunto;
  final Map<String, dynamic> resposta;
  final DateTime guardadaEm;
}
