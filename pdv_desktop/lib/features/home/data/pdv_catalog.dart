import 'dart:async';
import 'dart:convert';

import '../../../core/network/response_cache.dart';
import 'pdv_repository.dart';

export 'pdv_catalog_model.dart';

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
    if (guardado == null) return _completarDoServidor(restaurantId);
    // A tela abre com o guardado — mesmo VELHO, depois de uma venda ou de
    // reiniciar o PDV — e relê em silêncio SÓ as listas que podem ter mudado.
    final paraReler = _consultasParaReler(restaurantId);
    if (paraReler.isNotEmpty) {
      unawaited(_revalidar(restaurantId, guardado, paraReler));
    }
    return guardado;
  }

  /// Busca só as listas que faltam no cache; as outras vêm de lá.
  ///
  /// Uma venda apaga comandas e mesas, e nada mais. Exigir o catálogo inteiro
  /// fazia o PDV baixar as seis listas — o cardápio inclusive — depois de
  /// TODA venda. Agora sobem duas.
  Future<PdvCatalog> _completarDoServidor(String restaurantId) async {
    final consultas = _consultasDoCatalogo(restaurantId);
    final guardadas = [
      for (final (path, query, paginada) in consultas)
        paginada ? _peekAll(path, query) : _peekOne(path, query),
    ];
    if (guardadas.every((lista) => lista == null)) {
      return _loadCatalogFromServer(restaurantId);
    }
    final listas = await Future.wait([
      for (var i = 0; i < consultas.length; i++)
        if (guardadas[i] case final lista?)
          Future.value(lista)
        else if (consultas[i].$3)
          listAll(consultas[i].$1, query: consultas[i].$2)
        else
          list(consultas[i].$1, query: consultas[i].$2),
    ]);
    return PdvCatalog.fromLists(listas);
  }

  Future<void> _revalidar(
    String restaurantId,
    PdvCatalog mostrado,
    List<(String, Map<String, dynamic>, bool)> consultas,
  ) async {
    try {
      await Future.wait([
        for (final (path, query, paginada) in consultas)
          paginada ? listAll(path, query: query) : list(path, query: query),
      ]);
      final atual = cachedCatalog(restaurantId);
      if (atual != null &&
          jsonEncode(atual.toJson()) != jsonEncode(mostrado.toJson())) {
        api.signals.emit('realtime:pdv');
      }
    } catch (_) {
      // A tela já tem a última versão; o próximo evento ou abertura relê.
    }
  }

  /// As listas velhas (escrita, evento, reconexão, disco) ou passadas da
  /// janela de revalidação.
  List<(String, Map<String, dynamic>, bool)> _consultasParaReler(
    String restaurantId,
  ) => [
    for (final consulta in _consultasDoCatalogo(restaurantId))
      if ((api.cacheAge(
                consulta.$1,
                query: consulta.$3 ? {...consulta.$2, 'page': 1} : consulta.$2,
                accessToken: accessToken,
              ) ??
              ResponseCache.idadeDaVelha) >
          catalogRevalidateAfter)
        consulta,
  ];

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
