import 'dart:async';

import 'pdv_repository.dart';

/// Os produtos do PDV chegam em PÁGINAS: a primeira abre a venda, o resto vem
/// por trás.
///
/// O catálogo esperava TODAS as páginas de 300 produtos antes de mostrar a
/// grade — 5 a 7 s na nuvem a cada abertura sem cópia guardada (pdv.log:
/// 158 consultas por página). Agora a primeira página, menor, abre a venda; as
/// outras seguem em segundo plano, guardadas no cache como cada leitura, e no
/// fim o aviso `realtime:menu` faz a tela reler o catálogo, já inteiro, do cache.
///
/// O mesmo padrão das comandas (`command_pager.dart`): mostrar o que chegou,
/// e não esperar o último.
const produtosPorPagina = 60;

/// As cargas de fundo em curso, por consulta: duas aberturas seguidas não
/// disparam duas buscas do mesmo restante.
final _emCurso = <String, Future<void>>{};

/// A primeira página, e se o servidor tem mais (que vêm por trás).
Future<({List<JsonMap> itens, bool incompleto})> produtosDaPrimeiraPagina(
  PdvRepository repo,
  String path,
  Map<String, dynamic> query,
) async {
  final primeira = await repo.api.get(
    path,
    query: {...query, 'page': 1},
    accessToken: repo.accessToken,
  );
  final itens = ((primeira['results'] ?? const []) as List).cast<JsonMap>();
  final temMais = primeira['next'] != null && itens.isNotEmpty;
  if (temMais) {
    final chave = '$path?$query';
    _emCurso[chave] ??= _restante(
      repo,
      path,
      query,
      desde: 2,
    ).whenComplete(() => _emCurso.remove(chave));
  }
  return (itens: itens, incompleto: temMais);
}

/// As páginas seguintes, uma a uma: cada uma fica no cache ao chegar.
Future<void> _restante(
  PdvRepository repo,
  String path,
  Map<String, dynamic> query, {
  required int desde,
}) async {
  try {
    var total = 0;
    for (
      var pagina = desde;
      total < PdvRepository.maximumCollectionSize;
      pagina++
    ) {
      final resposta = await repo.api.get(
        path,
        query: {...query, 'page': pagina},
        accessToken: repo.accessToken,
      );
      final itens = (resposta['results'] ?? const []) as List;
      total += itens.length;
      if (itens.isEmpty || resposta['next'] == null) break;
    }
    // O catálogo agora está inteiro no cache: a tela relê dali (`menu` é a
    // recarga do catálogo, não da tela inteira).
    repo.api.signals.emit('realtime:menu');
  } catch (_) {
    // A venda segue com a primeira página; a próxima abertura completa.
  }
}
