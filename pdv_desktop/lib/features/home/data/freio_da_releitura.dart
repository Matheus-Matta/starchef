import 'dart:async';

/// No máximo uma releitura por [intervalo] de cada lista, quando quem pede é
/// um AVISO do servidor — e sempre uma última, depois que os avisos param.
///
/// Cada item lançado numa comanda, em qualquer aparelho da loja, avisa todos
/// os PDVs, e cada aviso marcava a lista de comandas como velha: todos relíam
/// as comandas INTEIRAS, em páginas de 300, uma vez por item. Numa hora de
/// movimento eram dezenas de releituras por minuto por caixa, o servidor
/// engasgava e a venda travava junto.
///
/// O freio não perde mudança: o aviso que chega dentro do intervalo agenda
/// UMA releitura para o fim dele ([depois]). A lista fica no máximo
/// [intervalo] atrás — e só a lista de apoio da tela: abrir, lançar e cobrar
/// uma comanda leem a própria comanda do servidor. A escrita feita AQUI não
/// passa pelo freio (ela não é aviso).
class FreioDaReleitura {
  FreioDaReleitura({
    this.intervalo = const Duration(seconds: 15),
    DateTime Function()? agora,
  }) : _agora = agora ?? DateTime.now;

  final Duration intervalo;
  final DateTime Function() _agora;
  final _ultima = <String, DateTime>{};
  final _adiadas = <String, Timer>{};

  /// A lista [chave] pode ser relida agora? Se não, [depois] roda no fim do
  /// intervalo (uma vez só, por mais avisos que cheguem até lá).
  bool podeReler(String chave, {required void Function() depois}) {
    final agora = _agora();
    final ultima = _ultima[chave];
    if (ultima == null || agora.difference(ultima) >= intervalo) {
      _ultima[chave] = agora;
      _adiadas.remove(chave)?.cancel();
      return true;
    }
    _adiadas[chave] ??= Timer(intervalo - agora.difference(ultima), () {
      _adiadas.remove(chave);
      depois();
    });
    return false;
  }

  bool temAdiada(String chave) => _adiadas.containsKey(chave);

  void dispose() {
    for (final timer in _adiadas.values) {
      timer.cancel();
    }
    _adiadas.clear();
  }
}

/// Um freio por processo: o repositório é recriado a cada tela. O fim do
/// intervalo avisa `realtime:tables`, e a tela relê o que ainda está velho.
final freioDoAviso = FreioDaReleitura();

/// As listas que o aviso mais faz reler, e as mais pesadas.
const listasComFreio = {'/commands/', '/tables/'};
