/// Os registros que a NUVEM criou ou devolveu enquanto a loja estava fora.
///
/// O terminal abre o pedido na nuvem com a loja fora; a janela do veredito
/// acaba, ele volta para a loja — e o pedido ainda não desceu pela
/// sincronização. O próximo gesto sobre ele (incluir item, receber) levava
/// "404 pedido não encontrado" e a conta ficava aberta: achado pela simulação
/// do dia a dia (`loadtest/dia_a_dia`).
///
/// Com isto, um 404 da loja num caminho que cita um id nascido na nuvem é
/// repetido na nuvem. É seguro: um 404 diz que a loja não executou nada.
class AfinidadeComANuvem {
  AfinidadeComANuvem({DateTime Function()? relogio})
    : _agora = relogio ?? DateTime.now;

  /// Mais que o tempo que a sincronização leva para descer o registro.
  static const validade = Duration(minutes: 10);
  static const _maximo = 500;

  final DateTime Function() _agora;
  final _ids = <String, DateTime>{};

  void lembrar(Map<String, dynamic> resposta) {
    final id = resposta['id'];
    if (id is! String || id.isEmpty) return;
    _ids[id] = _agora();
    if (_ids.length > _maximo) _ids.remove(_ids.keys.first);
  }

  /// O caminho cita um registro que nasceu na nuvem há pouco?
  bool tocaNaNuvem(String path) {
    final agora = _agora();
    _ids.removeWhere((_, quando) => agora.difference(quando) > validade);
    return _ids.keys.any(path.contains);
  }
}
