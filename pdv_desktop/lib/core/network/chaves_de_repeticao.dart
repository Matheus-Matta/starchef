import 'dart:convert';

/// A repetição IDÊNTICA de uma escrita que falhou na rede reaproveita a chave.
///
/// Wi-Fi que cai por 15 s: a requisição fica no ar, o terminal desiste e o
/// operador repete o gesto. A repetição saía com `Idempotency-Key` NOVA; quando
/// a rede voltava, as duas chegavam e o servidor gravava as duas — o item e a
/// pesagem em dobro na comanda (simulação do dia a dia, `loadtest/dia_a_dia`).
///
/// Mesma rota e mesmo corpo, pouco depois de uma falha de rede, é a mesma
/// operação: com a mesma chave o servidor grava uma vez e devolve a resposta
/// que já deu. Se a primeira de fato não chegou, a repetição executa — nada se
/// perde. Sucesso esquece a chave: o próximo gesto igual é uma operação nova.
class ChavesDeRepeticao {
  ChavesDeRepeticao({DateTime Function()? relogio})
    : _agora = relogio ?? DateTime.now;

  static const validade = Duration(minutes: 2);

  final DateTime Function() _agora;
  final _chaves = <String, (String, DateTime)>{};

  static String assinatura(String method, String path, Object? body) =>
      '$method $path ${jsonEncode(body)}';

  String? chaveDe(String assinatura) {
    final agora = _agora();
    _chaves.removeWhere((_, valor) => agora.difference(valor.$2) > validade);
    return _chaves[assinatura]?.$1;
  }

  void guardar(String assinatura, String chave) =>
      _chaves[assinatura] = (chave, _agora());

  void esquecer(String assinatura) => _chaves.remove(assinatura);
}
