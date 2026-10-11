import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'response_cache_disco.dart';

/// Última resposta das LISTAS, para a tela abrir na hora.
///
/// Não é fonte de verdade — o servidor continua sendo. A tela mostra o que
/// tinha e relê em silêncio; a leitura nova substitui. Por isso:
///
/// * entram listas de cadastro (comandas, produtos, categorias, clientes,
///   mesas, formas de pagamento, estações, impressoras) e a LISTA de pedidos,
///   só para exibir; caixa, autenticação e o pedido aberto, nunca — nada aqui
///   decide pagamento nem fechamento;
/// * a chave leva servidor, conta, usuário, rota e parâmetros: outra conta no
///   mesmo computador nunca vê a lista desta;
/// * escrita, evento de tempo real e reconexão NÃO apagam: marcam como VELHA
///   ([estaVelha]). A tela continua mostrando e quem lê relê em segundo plano
///   — apagar fazia o próximo gesto esperar o servidor, com tela de carregando;
/// * logout e troca de servidor apagam tudo; com [arquivo], sobrevive a
///   reiniciar o PDV (volta VELHO); limite [maxEntries] e validade [maxAge].
class ResponseCache {
  ResponseCache({
    this.maxEntries = 120,
    this.maxAge = const Duration(hours: 24),
    DateTime Function()? clock,
    File? arquivo,
  }) : _clock = clock ?? DateTime.now,
       _disco = arquivo == null ? null : DiscoDoCache(arquivo) {
    _disco?.carregar(
      _entries,
      (assunto, resposta, quando) =>
          EntradaDoCache(assunto, resposta, quando, velha: true),
    );
  }

  final int maxEntries;
  final Duration maxAge;
  final DateTime Function() _clock;
  final DiscoDoCache? _disco;
  // Literal de mapa do Dart guarda a ordem de inserção: a primeira chave é a
  // mais antiga, e é ela que sai quando o limite estoura.
  final _entries = <String, EntradaDoCache>{};

  /// A idade de uma VELHA: maior que qualquer janela de revalidação.
  static const idadeDaVelha = Duration(days: 3650);

  /// Rotas que entram, e o assunto de cada uma.
  static const _assuntos = {
    '/commands/': 'commands',
    '/menu/products/': 'menu',
    '/menu/categories/': 'menu',
    '/customers/': 'customers',
    '/tables/': 'tables',
    '/payments/methods/': 'payments',
    '/cash-stations/': 'cash',
    // A escolha da impressora do recibo lia esta lista a cada venda.
    '/printers/': 'printers',
    // A tela de pedidos abria vazia, carregando, a cada visita.
    '/orders/': 'orders',
  };

  /// O que uma escrita em cada rota pode ter mudado. Pedido mexe em comanda
  /// (anexar, cobrar, liberar), em mesa e na lista de pedidos.
  static const _escritaAfeta = {
    'commands': {'commands', 'tables'},
    'orders': {'commands', 'tables', 'orders'},
    'menu': {'menu'},
    'customers': {'customers'},
    'tables': {'tables', 'commands'},
    'payments': {'payments'},
    'cash-stations': {'cash'},
    'cash-register': {'cash'},
    'printers': {'printers'},
  };

  static String? assuntoDe(String path) => _assuntos[path];

  int get length => _entries.length;

  String chave(String escopo, String path, Map<String, dynamic>? query) {
    final ordenada = SplayTreeMap<String, String>.from(
      (query ?? const {}).map((k, v) => MapEntry(k, '$v')),
    );
    return '$escopo|$path?${jsonEncode(ordenada)}';
  }

  /// Guarda a resposta, se a rota entra no cache.
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
    _entries[k] = EntradaDoCache(assunto, resposta, _clock());
    while (_entries.length > maxEntries) {
      _entries.remove(_entries.keys.first);
    }
    _salvar();
  }

  /// A última resposta guardada (mesmo VELHA), ou `null` se não há ou venceu.
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

  /// Há quanto tempo foi guardada — [idadeDaVelha] se ficou velha.
  Duration? ageOf(String escopo, String path, Map<String, dynamic>? query) {
    final entrada = _entries[chave(escopo, path, query)];
    if (entrada == null) return null;
    if (entrada.velha) return idadeDaVelha;
    return _clock().difference(entrada.guardadaEm);
  }

  /// Algo pode ter mudado desde que foi guardada: quem lê deve reler.
  bool estaVelha(String escopo, String path, Map<String, dynamic>? query) =>
      _entries[chave(escopo, path, query)]?.velha ?? false;

  /// Uma escrita deste terminal: marca como velho o que ela pode ter mudado.
  void invalidateForWrite(String path) {
    final segmentos = path.split('/').where((s) => s.isNotEmpty).toList();
    if (segmentos.isEmpty) return;
    invalidate(_escritaAfeta[segmentos.first] ?? const {});
  }

  /// Um evento do servidor (`restaurants.command`, `menu.product`…).
  void invalidateForResource(String resource) {
    final app = resource.split('.').first;
    final modelo = resource.contains('.') ? resource.split('.').last : '';
    if (app == 'printers') {
      // Trabalho de impressão chega a CADA cupom. Só o cadastro da impressora
      // muda a lista.
      if (modelo == 'printer') invalidate({'printers'});
      return;
    }
    final assuntos = <String>{
      if (app == 'orders') ...{'commands', 'tables', 'orders'},
      if (app == 'menu') 'menu',
      if (app == 'customers') 'customers',
      if (app == 'payments') ...{'payments', 'cash', 'orders'},
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

  /// Marca como VELHO (não apaga): a tela segue mostrando e relê.
  void invalidate(Set<String> assuntos) {
    for (final entrada in _entries.values) {
      if (assuntos.contains(entrada.assunto)) entrada.velha = true;
    }
    _salvar();
  }

  /// Tudo velho — a reconexão do tempo real: eventos podem ter se perdido.
  void envelhecer() => invalidate(_assuntos.values.toSet());

  /// Logout e troca de servidor: outro mundo, nada daqui serve.
  void clear() {
    _entries.clear();
    _salvar();
  }

  void _salvar() => _disco?.salvar(_entries, (entrada) => entrada.toJson());
}
