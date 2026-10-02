import 'dart:async';
import 'dart:convert';

import 'pdv_repository.dart';

/// Abaixo disso a cópia acabou de vir do servidor: reler seria em dobro.
const catalogRevalidateAfter = Duration(seconds: 10);

/// O catálogo do PDV: carga do servidor e a última cópia para abrir na hora.
extension CatalogoDoPdv on PdvRepository {
  /// O catálogo — o último que se viu primeiro, quando há um inteiro.
  ///
  /// Com o catálogo inteiro no cache ([ApiClient.cache]), a tela abre na hora
  /// e a releitura roda por trás; se algo mudou, `realtime:pdv` faz a tela
  /// redesenhar (ela já escuta esse sinal). Sem catálogo inteiro, lê do
  /// servidor como sempre. Escrita e evento do assunto apagam a entrada, então
  /// depois de uma mudança a leitura vai ao servidor.
  Future<PdvCatalog> loadCatalog(String restaurantId) async {
    final guardado = cachedCatalog(restaurantId);
    if (guardado == null) return _loadCatalogFromServer(restaurantId);
    if (_idadeDoCatalogo(restaurantId) > catalogRevalidateAfter) {
      unawaited(_revalidar(restaurantId, guardado));
    }
    return guardado;
  }

  Future<void> _revalidar(String restaurantId, PdvCatalog mostrado) async {
    try {
      final atual = await _loadCatalogFromServer(restaurantId);
      if (jsonEncode(atual.toJson()) != jsonEncode(mostrado.toJson())) {
        api.signals.emit('realtime:pdv');
      }
    } catch (_) {
      // A tela já tem a última versão; o próximo evento ou abertura relê.
    }
  }

  List<(String, Map<String, dynamic>, bool)> _consultasDoCatalogo(
    String restaurantId,
  ) {
    final query = {'page_size': 300, 'restaurant': restaurantId};
    return [
      ('/cash-stations/', {...query, 'is_active': true}, false),
      ('/menu/products/', {...query, 'is_active': true}, true),
      ('/menu/categories/', {'page_size': 100, 'is_active': true}, false),
      ('/tables/', query, true),
      ('/commands/', {...query, 'is_active': true}, true),
      (
        '/payments/methods/',
        {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
        false,
      ),
    ];
  }

  /// O catálogo montado só do cache, ou `null` se falta qualquer página.
  PdvCatalog? cachedCatalog(String restaurantId) {
    final listas = <List<JsonMap>>[];
    for (final (path, query, paginada) in _consultasDoCatalogo(restaurantId)) {
      final lista = paginada ? _peekAll(path, query) : _peekOne(path, query);
      if (lista == null) return null;
      listas.add(lista);
    }
    return PdvCatalog.fromLists(listas);
  }

  Duration _idadeDoCatalogo(String restaurantId) {
    var maisVelha = Duration.zero;
    for (final (path, query, paginada) in _consultasDoCatalogo(restaurantId)) {
      final idade = api.cacheAge(
        path,
        query: paginada ? {...query, 'page': 1} : query,
        accessToken: accessToken,
      );
      if (idade != null && idade > maisVelha) maisVelha = idade;
    }
    return maisVelha;
  }

  List<JsonMap>? _peekOne(String path, Map<String, dynamic> query) {
    final resposta = api.peek(path, query: query, accessToken: accessToken);
    if (resposta == null) return null;
    return ((resposta['results'] ?? const []) as List).cast<JsonMap>();
  }

  List<JsonMap>? _peekAll(String path, Map<String, dynamic> query) {
    final juntos = <JsonMap>[];
    for (
      var page = 1;
      juntos.length < PdvRepository.maximumCollectionSize;
      page++
    ) {
      final resposta = api.peek(
        path,
        query: {...query, 'page': page},
        accessToken: accessToken,
      );
      if (resposta == null) return null;
      juntos.addAll(
        ((resposta['results'] ?? const []) as List).cast<JsonMap>(),
      );
      if (resposta['next'] == null) return juntos;
    }
    return juntos;
  }

  Future<PdvCatalog> _loadCatalogFromServer(String restaurantId) async {
    final query = {'page_size': 300, 'restaurant': restaurantId};
    final responses = await Future.wait([
      list('/cash-stations/', query: {...query, 'is_active': true}),
      // Produtos, mesas e comandas crescem sem teto: um restaurante com 400
      // itens no cardápio ou 1.000 cartões de comanda é rotina. Estas três
      // seguem `next` até o fim; as demais cabem em uma página.
      listAll('/menu/products/', query: {...query, 'is_active': true}),
      list('/menu/categories/', query: {'page_size': 100, 'is_active': true}),
      listAll('/tables/', query: query),
      // Mesas servem ao vínculo opcional da comanda; comandas são o contexto
      // de abertura do pedido.
      listAll('/commands/', query: {...query, 'is_active': true}),
      // Exatamente a mesma consulta da tela de recebimento: a mesma entrada
      // do cache serve às duas.
      list(
        '/payments/methods/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      ),
    ]);
    return PdvCatalog.fromLists(responses);
  }
}

class PdvCatalog {
  const PdvCatalog({
    required this.cashStations,
    required this.products,
    required this.categories,
    required this.tables,
    required this.commands,
    required this.paymentMethods,
  });

  /// Na ordem de [CatalogoDoPdv._consultasDoCatalogo].
  factory PdvCatalog.fromLists(List<List<JsonMap>> listas) => PdvCatalog(
    cashStations: listas[0],
    products: listas[1],
    categories: listas[2],
    tables: listas[3],
    commands: listas[4],
    paymentMethods: listas[5],
  );

  Map<String, dynamic> toJson() => {
    'cash_stations': cashStations,
    'products': products,
    'categories': categories,
    'tables': tables,
    'commands': commands,
    'payment_methods': paymentMethods,
  };

  final List<JsonMap> cashStations;
  final List<JsonMap> products;
  final List<JsonMap> categories;
  final List<JsonMap> tables;
  final List<JsonMap> commands;
  final List<JsonMap> paymentMethods;
}
