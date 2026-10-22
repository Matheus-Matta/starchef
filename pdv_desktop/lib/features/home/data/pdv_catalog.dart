import 'dart:async';
import 'dart:convert';

import '../../../core/network/response_cache.dart';
import 'freio_da_releitura.dart';
import 'pdv_repository.dart';
import 'produtos_em_paginas.dart';

export 'pdv_catalog_model.dart';

/// Lista que NENHUM aviso marcou como velha só é relida depois disto.
///
/// Eram 10 s: como a tela recarrega a cada aviso da loja (um item na comanda,
/// um pagamento), o cardápio inteiro era relido o tempo todo — 316 leituras
/// de produtos em 50 minutos, 13 s cada, no pdv.log de um caixa travando. O
/// que mudou de fato chega marcado como velho (`ResponseCache.invalidate`) e é
/// relido na hora; isto é só a rede de segurança para aviso perdido.
const catalogRevalidateAfter = Duration(minutes: 5);

/// A lista do catálogo precisa ser relida? Velha (aviso, escrita, reconexão)
/// ou guardada há mais de [catalogRevalidateAfter].
bool listaDoCatalogoPrecisaReler(Duration? idade) =>
    (idade ?? ResponseCache.idadeDaVelha) > catalogRevalidateAfter;

/// O catálogo do PDV: carga do servidor e a última cópia para abrir na hora.
extension CatalogoDoPdv on PdvRepository {
  /// O catálogo — o último que se viu primeiro, quando há um inteiro.
  ///
  /// Com o catálogo inteiro no cache ([ApiClient.cache]), a tela abre na hora
  /// e a releitura roda por trás; se algo mudou, `realtime:pdv` faz a tela
  /// redesenhar (ela já escuta esse sinal). Sem catálogo inteiro, lê do
  /// servidor como sempre. Escrita e evento do assunto apagam a entrada, então
  /// depois de uma mudança a leitura vai ao servidor.
  ///
  /// [porAviso]: a carga veio de um aviso do servidor, e não de gesto daqui;
  /// comandas e mesas passam pelo [freioDoAviso].
  Future<PdvCatalog> loadCatalog(
    String restaurantId, {
    bool porAviso = false,
  }) async {
    final guardado = cachedCatalog(restaurantId);
    if (guardado == null) return _completarDoServidor(restaurantId);
    // A tela abre com o guardado — mesmo VELHO, depois de uma venda ou de
    // reiniciar o PDV — e relê em silêncio SÓ as listas que podem ter mudado.
    final paraReler = [
      for (final consulta in _consultasParaReler(restaurantId))
        if (!porAviso ||
            !listasComFreio.contains(consulta.$1) ||
            freioDoAviso.podeReler(
              '$restaurantId${consulta.$1}',
              depois: () => api.signals.emit('realtime:tables'),
            ))
          consulta,
    ];
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
  ///
  /// Os PRODUTOS não esperam o cardápio inteiro: a primeira página abre a
  /// venda e o resto chega por trás (`produtos_em_paginas.dart`).
  Future<PdvCatalog> _completarDoServidor(String restaurantId) async {
    final consultas = _consultasDoCatalogo(restaurantId);
    final guardadas = [
      for (final (path, query, paginada) in consultas)
        paginada ? _peekAll(path, query) : _peekOne(path, query),
    ];
    var incompleto = false;
    Future<List<JsonMap>> produtos(String path, Map<String, dynamic> q) async {
      final primeira = await produtosDaPrimeiraPagina(this, path, q);
      incompleto = primeira.incompleto;
      return primeira.itens;
    }

    final listas = await Future.wait([
      for (var i = 0; i < consultas.length; i++)
        if (guardadas[i] case final lista?)
          Future.value(lista)
        else if (consultas[i].$1 == '/menu/products/')
          produtos(consultas[i].$1, consultas[i].$2)
        else if (consultas[i].$3)
          listAll(consultas[i].$1, query: consultas[i].$2)
        else
          list(consultas[i].$1, query: consultas[i].$2),
    ]);
    return PdvCatalog.fromLists(listas, carregandoProdutos: incompleto);
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
        // `menu`, e não `pdv`: só o catálogo mudou, e `pdv` recarregava a
        // tela inteira (restaurantes, caixa, agente de impressão).
        api.signals.emit('realtime:menu');
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
      if (listaDoCatalogoPrecisaReler(
        api.cacheAge(
          consulta.$1,
          query: consulta.$3 ? {...consulta.$2, 'page': 1} : consulta.$2,
          accessToken: accessToken,
        ),
      ))
        consulta,
  ];

  List<(String, Map<String, dynamic>, bool)> _consultasDoCatalogo(
    String restaurantId,
  ) {
    final query = {'page_size': 300, 'restaurant': restaurantId};
    return [
      ('/cash-stations/', {...query, 'is_active': true}, false),
      (
        '/menu/products/',
        // Página menor: é a primeira que abre a venda (`produtos_em_paginas`).
        {...query, 'page_size': produtosPorPagina, 'is_active': true},
        true,
      ),
      ('/menu/categories/', {'page_size': 100, 'is_active': true}, false),
      ('/tables/', query, true),
      ('/commands/', {...query, 'is_active': true}, true),
      (
        '/payments/methods/',
        {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
          // A mais usada primeiro (90 dias): o PDV abre o pagamento nela.
          'ordering': '-uso,name',
        },
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
}
